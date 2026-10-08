"""Views for task2_support app.

Handles:
1. chat_ui: Rendering modern multi-turn support interface.
2. api_support_chat: RAG retrieval, Gemini LLM chat with conversation history (up to 10+ turns),
   anti-repetition safeguards, graceful topic switching, and mandatory document citations.
3. api_reset: Session reset for clean demonstration runs.
"""
import json
import logging
import re
from typing import List, Dict, Any, Optional
from django.conf import settings
from django.http import JsonResponse, HttpRequest
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie, csrf_exempt
from django.views.decorators.http import require_http_methods

from .engine import RAG_ENGINE, get_relevant_context, format_context, STOP_WORDS
from .memory import SessionMemory, get_session_memory, save_session_memory, clear_session_memory, compute_cosine_similarity

logger = logging.getLogger(__name__)

# Key & Model performance cache
_EXCLUDED_MODELS = set()
_QUOTA_EXHAUSTED_KEYS = {}

SYSTEM_PROMPT = (
    "You are a document-grounded support assistant.\n"
    "Rules:\n"
    "1) Answer ONLY from RETRIEVED DOCUMENT CONTEXT below. If missing, say you cannot find it in the documents.\n"
    "2) Use chat history for follow-ups (e.g. 'the second method', 'what about P3?') — resolve references from prior turns.\n"
    "3) Do NOT repeat full policy paragraphs already given; add new detail or a one-line recap when the user asks to be reminded.\n"
    "4) On topic change, one short bridge sentence, then answer the new topic.\n"
    "5) Every factual sentence must include a citation: [Doc: <file>, Page: <n>, Section: <title>].\n"
    "6) Be concise (2–6 sentences unless the user asks for a list).\n"
    "7) ONE document per answer: use only PRIMARY DOCUMENT excerpts. Never blend SLA text with billing or security files."
)

GEMINI_MODEL_CANDIDATES = [
    "gemini-3.5-flash-lite",
    "gemini-3.5-flash",
    "gemini-3.8-flash",
    "gemini-3.1-flash-lite",
    "gemini-flash-latest",
    "gemini-flash-lite-latest",
]


def is_person_lookup_query(message: str) -> bool:
    low = message.lower().strip()
    return bool(
        re.match(r'^(who\s+is|who\'s|who\s+was|tell\s+me\s+about)\s+([a-z\s]+)$', low)
        and not any(w in low for w in [
            'skill', 'skills', 'project', 'projects', 'education', 'degree',
            'experience', 'work', 'email', 'phone', 'contact', 'salary', 'stipend',
            'policy', 'rule', 'terms', 'sla', 'pricing', 'refund', 'what', 'how', 'which'
        ])
    )


def extract_lookup_entity(message: str) -> str:
    low = message.lower()
    m = re.search(r'\b(?:do you know|who is|who\'s|tell me about)\s+([a-z][a-z\s\-]{1,40})', low)
    if m:
        return m.group(1).strip().title()
    words = [w for w in re.findall(r'\b[A-Za-z]{3,}\b', message) if w.lower() not in STOP_WORDS]
    return words[-1].title() if words else ""


def truncate_grounded_text(text: str, max_len: int = 300) -> str:
    flat = re.sub(r'\s+', ' ', (text or "").strip())
    if len(flat) <= max_len:
        return flat
    cut = flat[: max_len - 1].rsplit(' ', 1)[0]
    return cut + '…'


def stem_token(word: str) -> str:
    """Lightweight token stemming for robust keyword retrieval."""
    w = word.lower()
    for suff in ['ing', 'ed', 'es', 's']:
        if w.endswith(suff) and len(w) > len(suff) + 2:
            return w[:-len(suff)]
    return w


def extract_coherent_blocks(text: str) -> List[str]:
    """Extracts complete paragraphs or bullet items, keeping multi-line wrapped points together."""
    blocks = []
    current_block = []
    for line in text.split('\n'):
        line_stripped = line.strip()
        if not line_stripped:
            if current_block:
                blocks.append(' '.join(current_block))
                current_block = []
            continue
        # Headers or list markers start a new block
        if line_stripped.startswith(('##', '#', '-', '*', '•')) or re.match(r'^\d+\.', line_stripped):
            if current_block:
                blocks.append(' '.join(current_block))
                current_block = []
            current_block.append(line_stripped)
        else:
            if current_block:
                current_block.append(line_stripped)
            else:
                current_block.append(line_stripped)
    if current_block:
        blocks.append(' '.join(current_block))
    return blocks


def score_block_relevance(query: str, block: str) -> float:
    """Scores how well a text block answers the user query using token overlap and domain signals."""
    q_tokens = [stem_token(w) for w in re.findall(r'\b[a-zA-Z0-9]+\b', query.lower()) 
                if (len(w) >= 2 and w not in STOP_WORDS) or any(c.isdigit() for c in w)]
    b_tokens = [stem_token(w) for w in re.findall(r'\b[a-zA-Z0-9]+\b', block.lower())]
    if not q_tokens or not b_tokens:
        return 0.0

    score = 0.0
    for qw in q_tokens:
        if qw in b_tokens:
            score += 2.0
        elif any(qw in bt for bt in b_tokens):
            score += 1.0

    q_low = query.lower()
    b_low = block.lower()
    if 'lost in transit' in q_low and 'lost in transit' in b_low:
        score += 5.0
    if 'warranty' in q_low and ('exclusions' in b_low or 'liquid' in b_low or 'drop' in b_low):
        score += 5.0
    if 'refund' in q_low and 'days' in q_low and ('processing timeline' in b_low or 'business days' in b_low):
        score += 5.0
    if 'p1' in q_low and 'p1' in b_low:
        score += 5.0
    if 'p3' in q_low and 'p3' in b_low:
        score += 5.0
    if ('recovery codes' in q_low or 'password' in q_low) and 'lost' in q_low and 'manual verification' in b_low:
        score += 6.0
    if 'mfa' in q_low or 'multi-factor' in q_low:
        if 'mandatory' in q_low and 'mandatory enforcement' in b_low:
            score += 5.0
    if 'professional' in q_low and 'professional plan' in b_low:
        score += 5.0

    if is_person_lookup_query(query):
        entity = extract_lookup_entity(query).lower()
        if entity and entity in b_low:
            score += 25.0

    return score


@ensure_csrf_cookie
def chat_ui(request: HttpRequest):
    """Renders the Task 2 Smart Support Assistant UI."""
    memory = get_session_memory(request)
    context = {
        "indexed_chunks_count": (
            RAG_ENGINE._collection.count()
            if RAG_ENGINE._collection and RAG_ENGINE._collection.count() > 0
            else len(RAG_ENGINE._in_memory_chunks)
        ),
        "turn_count": memory.turn_count,
        "active_topic": memory.active_topic or 'General Support',
        "uploaded_files": RAG_ENGINE.get_uploaded_documents(),
    }
    return render(request, 'task2_support/index.html', context)


@csrf_exempt
@require_http_methods(["POST"])
def api_support_chat(request: HttpRequest) -> JsonResponse:
    """Multi-turn RAG chat endpoint using Gemini LLM and ChromaDB vector context."""
    try:
        data = json.loads(request.body.decode('utf-8'))
        user_message = data.get('message', '').strip()
        chat_id = data.get('chat_id')
    except Exception:
        return JsonResponse({"error": "Invalid JSON payload in request body"}, status=400)

    if not user_message:
        return JsonResponse({"error": "Message cannot be empty"}, status=400)

    # 1. Retrieve session memory
    memory = get_session_memory(request, chat_id=chat_id)
    turn_number = memory.turn_count + 1
    history = memory.get_chat_history(max_turns=10)
    topic_history = list(memory.topic_history)
    active_topic = memory.active_topic

    # Track active document if provided or uploaded
    active_doc_param = data.get('active_document')
    if active_doc_param:
        memory.active_document = active_doc_param

    # Detect if query refers to "this pdf", "this file", "this document", "what is this related to", etc.
    is_referencing_current_doc = bool(
        re.search(r'\b(this|the|my|uploaded|current)\s+(pdf|document|doc|file|image|card|sheet|paper)\b', user_message.lower())
        or re.search(r'\b(what is this|what does this|who is this|summarize this|tell me about this|related to what|what is in this)\b', user_message.lower())
    )

    uploaded_docs = RAG_ENGINE.get_uploaded_documents()
    latest_uploaded = uploaded_docs[-1]['name'] if uploaded_docs else None
    explicit_file = RAG_ENGINE.detect_filename_in_query(user_message)

    retrieval_query = memory.build_retrieval_query(user_message)
    source_lock = None

    if explicit_file:
        source_lock = explicit_file
        memory.active_document = explicit_file
        relevant_chunks = get_relevant_context(retrieval_query, top_k=5, source_file_lock=source_lock)
    elif is_referencing_current_doc:
        source_lock = memory.active_document or latest_uploaded
        if source_lock and len(user_message.split()) <= 8:
            clean_stem = re.sub(r'[\.\-_]', ' ', source_lock)
            retrieval_query = f"{retrieval_query} {clean_stem}"
        relevant_chunks = get_relevant_context(retrieval_query, top_k=5, source_file_lock=source_lock)
    else:
        # Search globally across the knowledge base to detect which document best answers the query
        global_chunks = get_relevant_context(retrieval_query, top_k=8, source_file_lock=None)

        if global_chunks:
            top_file = global_chunks[0].get("source_file")

            # Compare relevance of active document vs top candidate across chunks
            if memory.active_document and top_file != memory.active_document:
                top_score = RAG_ENGINE._chunk_score(user_message, global_chunks[0])
                active_chunks = [c for c in global_chunks if c.get("source_file") == memory.active_document]
                active_score = RAG_ENGINE._chunk_score(user_message, active_chunks[0]) if active_chunks else 0.0

                # Only keep active document if query is an ambiguous follow-up AND active document has comparable score
                if memory.is_likely_follow_up(user_message) and active_score > 5.0 and active_score >= top_score - 4.0:
                    top_file = memory.active_document

            source_lock = top_file
            relevant_chunks = [c for c in global_chunks if c.get("source_file") == top_file][:5]
            if len(relevant_chunks) < 3 and top_file:
                doc_specific = get_relevant_context(retrieval_query, top_k=5, source_file_lock=top_file)
                if doc_specific:
                    relevant_chunks = doc_specific
        else:
            relevant_chunks = []

    if source_lock:
        memory.active_document = source_lock
        if source_lock not in memory.covered_documents:
            memory.covered_documents.append(source_lock)

    formatted_context = format_context(relevant_chunks)
    session_brief = memory.get_session_brief(max_turns=8)

    # 3. Score candidate blocks across all retrieved chunks
    is_reminder = any(rem in user_message.lower() for rem in ['remind', 'repeat', 'again', 'what were', 'summarize'])
    scored_candidates = []

    for rank, chunk in enumerate(relevant_chunks):
        blocks = extract_coherent_blocks(chunk.get("text", ""))
        for b in blocks:
            clean_b = re.sub(r'^#{1,6}\s*[^\n]*\n?', '', b).strip()
            eval_block = clean_b if len(clean_b) > 20 else b
            if not eval_block.strip():
                continue
            norm_fact = re.sub(r'[^a-zA-Z0-9]', '', eval_block.lower()[:60])
            already = memory.has_fact_been_delivered(norm_fact)
            raw_sc = score_block_relevance(retrieval_query, eval_block)
            # Give semantic vector rank bonus (top vector matches from ChromaDB get priority)
            rank_bonus = max(0.0, 4.0 - rank * 1.5)
            eff_sc = raw_sc + rank_bonus
            if already and not is_reminder:
                eff_sc -= 10.0

            scored_candidates.append({
                'chunk': chunk,
                'block': eval_block,
                'norm_fact': norm_fact,
                'raw_score': raw_sc,
                'eff_score': eff_sc,
                'already_delivered': already
            })

    scored_candidates.sort(key=lambda x: x['eff_score'], reverse=True)
    best_candidate = scored_candidates[0] if scored_candidates else None

    # Topic & citation from reranked retrieval (best block only refines excerpt)
    if relevant_chunks:
        primary_chunk = relevant_chunks[0]
        current_topic = primary_chunk.get("section_title", "Customer Support Policy")
        primary_citation = primary_chunk.get("citation", "")
        primary_src = primary_chunk.get("source_file")
        if (
            best_candidate
            and best_candidate.get("eff_score", 0) >= 4.0
            and best_candidate["chunk"].get("source_file") == primary_src
        ):
            primary_chunk = best_candidate["chunk"]
            current_topic = primary_chunk.get("section_title", current_topic)
            primary_citation = primary_chunk.get("citation", primary_citation)
    elif best_candidate:
        primary_chunk = best_candidate["chunk"]
        current_topic = primary_chunk.get("section_title", "Customer Support Policy")
        primary_citation = primary_chunk.get("citation", "")
    else:
        primary_chunk = None
        current_topic = "General Support"
        primary_citation = "[Doc: Customer_Support_Policy.pdf, Page: 2, Section: Service Level Agreements (SLAs) & Response Windows]"
    if primary_chunk and primary_chunk.get("source_file"):
        doc_src = primary_chunk.get("source_file")
        memory.active_document = doc_src
        if doc_src not in memory.covered_documents:
            memory.covered_documents.append(doc_src)

    all_citations = [c.get("citation") for c in relevant_chunks if c.get("citation")]

    # 4. Topic Shift Detection
    is_topic_switch = bool(active_topic and active_topic != current_topic)
    returning_to_previous_topic = is_topic_switch and memory.has_topic_been_visited(current_topic)

    # 5. Anti-Repetition Guard: Check semantic cosine similarity and logged facts
    candidate_text = best_candidate['block'] if best_candidate else ""
    candidate_fact_keys = [best_candidate['norm_fact']] if (best_candidate and best_candidate['norm_fact']) else []
    anti_rep_triggered, max_cos_sim, already_count = memory.is_anti_repetition_triggered(
        candidate_text=candidate_text,
        candidate_fact_keys=candidate_fact_keys,
        cosine_threshold=0.85
    )

    # 6. Build Augmented Prompt with Directives
    prompt_guidance = []
    if is_topic_switch:
        prompt_guidance.append(
            f"[Directive: Context shifted to '{current_topic}'. Do not mention topic switching; answer directly.]"
        )

    if anti_rep_triggered or is_reminder:
        prompt_guidance.append(
            "[Directive: The user has previously received core information on this topic in earlier turns. "
            "Do NOT repeat the general baseline boilerplate. Directly answer their specific question with novel details or a concise summary.]"
        )

    guidance_block = ("\n" + "\n".join(prompt_guidance) + "\n") if prompt_guidance else ""
    augmented_user_prompt = (
        f"SESSION MEMORY (recent dialogue):\n{session_brief}\n\n"
        f"RETRIEVED DOCUMENT CONTEXT:\n{formatted_context}\n"
        f"{guidance_block}\n"
        f"USER MESSAGE:\n{user_message}"
    )

    # 7. Call LLM (Google Gemini with Multi-Key Pool & Fallback)
    reply_text = call_gemini_chat(
        history=history,
        augmented_user_prompt=augmented_user_prompt,
        user_message=user_message,
        scoring_query=retrieval_query,
        relevant_chunks=relevant_chunks,
        best_candidate=best_candidate,
        is_topic_switch=is_topic_switch,
        returning_to_previous_topic=returning_to_previous_topic,
        active_topic=active_topic,
        current_topic=current_topic,
        anti_rep_triggered=(anti_rep_triggered or is_reminder),
        primary_citation=primary_citation
    )

    # Ensure mandatory citation is present in the final reply
    found_citations = re.findall(r'\[Doc:\s*[^\]]+\]', reply_text)
    if found_citations:
        primary_citation = found_citations[0]
    elif primary_citation and primary_citation not in reply_text and "Doc:" not in reply_text:
        reply_text += f"\n\n**Official Citation:** `{primary_citation}`"

    # 8. Record Turn in Persistent Session Memory
    new_facts_to_log = [best_candidate['norm_fact']] if (best_candidate and best_candidate.get('norm_fact')) else []
    memory.record_turn(
        user_query=user_message,
        topic=current_topic,
        delivered_facts=new_facts_to_log,
        citation=primary_citation,
        assistant_reply=reply_text,
        citations=all_citations,
        source_file=(primary_chunk.get("source_file") if primary_chunk else ""),
    )
    save_session_memory(request, memory, chat_id=chat_id)

    sources = []
    for chunk in relevant_chunks[:3]:
        raw_text = (chunk.get("text") or "").strip()
        lines = []
        for line in raw_text.split('\n'):
            s = line.strip()
            if not s:
                continue
            s = re.sub(r'^#{1,6}\s*', '', s)
            lines.append(s)
        clean_excerpt = "\n\n".join(lines)
        if len(clean_excerpt) > 380:
            clean_excerpt = clean_excerpt[:377].rsplit(' ', 1)[0] + "…"

        sources.append({
            "citation": chunk.get("citation") or "",
            "excerpt": clean_excerpt,
        })

    return JsonResponse({
        "reply": reply_text,
        "citation": primary_citation,
        "citations": all_citations,
        "sources": sources,
        "topic": current_topic,
        "previous_topic": active_topic if is_topic_switch else None,
        "topics": memory.topic_history,
        "anti_repeat": bool(anti_rep_triggered or is_reminder),
        "is_topic_switch": is_topic_switch,
        "returning_to_previous_topic": returning_to_previous_topic,
        "turn_number": turn_number,
        "total_turns": memory.turn_count,
        "chat_id": chat_id,
        "source_file": primary_chunk.get("source_file") if primary_chunk else None,
        "active_document": memory.active_document,
        "covered_documents": list(memory.covered_documents),
    })


def call_gemini_chat(
    history: List[Dict[str, str]],
    augmented_user_prompt: str,
    user_message: str,
    scoring_query: str,
    relevant_chunks: List[Dict[str, Any]],
    best_candidate: Optional[Dict[str, Any]],
    is_topic_switch: bool,
    returning_to_previous_topic: bool,
    active_topic: Optional[str],
    current_topic: str,
    anti_rep_triggered: bool,
    primary_citation: str
) -> str:
    """Executes multi-turn conversation using google-generativeai SDK with automatic failover."""
    keys_pool = getattr(settings, 'GEMINI_API_KEYS', [])
    single_key = getattr(settings, 'GEMINI_API_KEY', '')
    if single_key and single_key not in keys_pool:
        keys_pool = [single_key] + keys_pool

    try:
        import google.generativeai as genai

        chat_history_payload = []
        for msg in history[-18:]:
            role = "user" if msg.get("role") == "user" else "model"
            chat_history_payload.append({
                "role": role,
                "parts": [msg.get("content", "")]
            })

        import time
        now = time.time()
        deadline = now + 15.0
        active_keys = [k for k in keys_pool if k and (_QUOTA_EXHAUSTED_KEYS.get(k, 0) + 120 < now)]

        for key_candidate in active_keys:
            if time.time() > deadline:
                break
            genai.configure(api_key=key_candidate)

            for model_name in GEMINI_MODEL_CANDIDATES:
                if time.time() > deadline:
                    break
                if model_name in _EXCLUDED_MODELS:
                    continue
                try:
                    model = genai.GenerativeModel(
                        model_name=model_name,
                        system_instruction=SYSTEM_PROMPT,
                    )
                    chat = model.start_chat(history=chat_history_payload)
                    try:
                        response = chat.send_message(
                            augmented_user_prompt,
                            request_options={"timeout": 12},
                        )
                    except TypeError:
                        response = chat.send_message(augmented_user_prompt)
                    if response and response.text:
                        return response.text.strip()
                except Exception as model_err:
                    err_str = str(model_err)
                    if "404" in err_str or "not found" in err_str.lower():
                        _EXCLUDED_MODELS.add(model_name)
                    elif "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                        _QUOTA_EXHAUSTED_KEYS[key_candidate] = time.time()
                        break
                    continue
    except Exception as general_err:
        logger.error(f"Failed invoking Gemini: {general_err}")

    # Deterministic high-precision fallback
    return synthesize_deterministic_support_reply(
        user_message=user_message,
        scoring_query=scoring_query or user_message,
        relevant_chunks=relevant_chunks,
        best_candidate=best_candidate,
        is_topic_switch=is_topic_switch,
        returning_to_previous_topic=returning_to_previous_topic,
        active_topic=active_topic,
        current_topic=current_topic,
        anti_rep_triggered=anti_rep_triggered,
        primary_citation=primary_citation
    )


def collect_grounded_snippets(
    user_message: str,
    relevant_chunks: List[Dict[str, Any]],
    max_snippets: int = 4,
) -> List[Dict[str, Any]]:
    """Pick highest-scoring lines/bullets across chunks for extractive answers."""
    snippets: List[Dict[str, Any]] = []
    primary_citation = (relevant_chunks[0].get("citation") if relevant_chunks else "") or ""
    for chunk in relevant_chunks:
        citation = chunk.get("citation") or ""
        meta = {
            "text": chunk.get("text") or "",
            "section_title": chunk.get("section_title") or "",
            "source_file": chunk.get("source_file") or "",
        }
        chunk_intent = RAG_ENGINE._intent_boost(user_message, meta)
        if citation == primary_citation:
            chunk_intent += 4.0
        for block in extract_coherent_blocks(chunk.get("text", "")):
            clean = re.sub(r'^#{1,6}\s*', '', block).strip()
            if clean.startswith(('- ', '• ', '– ')):
                clean = clean[2:].strip()
            if len(clean) < 25:
                continue
            score = score_block_relevance(user_message, clean) + chunk_intent
            line_meta = {**meta, "text": clean}
            score += RAG_ENGINE._intent_boost(user_message, line_meta) * 0.5
            if score <= 0:
                continue
            snippets.append({"text": clean, "score": score, "citation": citation})
    snippets.sort(key=lambda x: x["score"], reverse=True)
    if relevant_chunks:
        primary_src = relevant_chunks[0].get("source_file")
        same_file = [s for s in snippets if primary_src in (s.get("citation") or "")]
        if same_file:
            snippets = same_file
    if snippets and snippets[0]["score"] < 3.0:
        return snippets[:1]
    best_score = snippets[0]["score"] if snippets else 0.0
    trimmed = [s for s in snippets if s["score"] >= best_score * 0.72]
    return (trimmed or snippets)[:max_snippets]


def synthesize_deterministic_support_reply(
    user_message: str,
    scoring_query: str,
    relevant_chunks: List[Dict[str, Any]],
    best_candidate: Optional[Dict[str, Any]],
    is_topic_switch: bool,
    returning_to_previous_topic: bool,
    active_topic: Optional[str],
    current_topic: str,
    anti_rep_triggered: bool,
    primary_citation: str
) -> str:
    """Extractive, citation-backed fallback when the LLM is unavailable."""
    reply_parts: List[str] = []
    person_q = is_person_lookup_query(user_message)
    max_snippets = 1 if person_q else 2

    if anti_rep_triggered and not person_q:
        reply_parts.append("Brief recap:\n\n")

    snippets = collect_grounded_snippets(scoring_query, relevant_chunks, max_snippets=max_snippets)
    if not snippets and best_candidate and best_candidate.get("block"):
        snippets = [{
            "text": best_candidate["block"],
            "citation": primary_citation,
            "score": 1.0,
        }]

    if snippets:
        cite = snippets[0].get("citation") or primary_citation
        body = snippets[0]["text"]
        if body.startswith(('- ', '• ', '– ')):
            body = body[2:].strip()
        body = truncate_grounded_text(body, max_len=320 if person_q else 420)
        if person_q:
            entity = extract_lookup_entity(user_message)
            if entity and entity.lower() in body.lower():
                reply_parts.append(
                    f"Yes — **{entity}** is described in the knowledge base: {body}\n\n{cite}"
                )
            else:
                reply_parts.append(f"From the documents: {body}\n\n{cite}")
        else:
            lines = []
            for snip in snippets:
                scite = snip.get("citation") or primary_citation
                sbody = snip["text"]
                if sbody.startswith(('- ', '• ', '– ')):
                    sbody = sbody[2:].strip()
                sbody = truncate_grounded_text(sbody, max_len=380)
                lines.append(f"- {sbody} {scite}")
            reply_parts.append("\n".join(lines))
    elif relevant_chunks:
        chunk = relevant_chunks[0]
        cite = chunk.get("citation") or primary_citation
        excerpt = truncate_grounded_text(chunk.get("text") or "", max_len=320)
        if person_q:
            entity = extract_lookup_entity(user_message)
            reply_parts.append(f"Yes — **{entity}** is in `{chunk.get('source_file', 'document')}`: {excerpt}\n\n{cite}")
        else:
            reply_parts.append(f"{excerpt}\n\n{cite}")
    else:
        if person_q:
            entity = extract_lookup_entity(user_message)
            reply_parts.append(
                f"No indexed document mentions **{entity or 'that name'}**. Upload the relevant file or rephrase."
            )
        else:
            reply_parts.append(
                "Not found in the indexed documents. Rephrase or upload the file."
            )

    return "".join(reply_parts)


@csrf_exempt
@require_http_methods(["POST"])
def api_reset(request: HttpRequest) -> JsonResponse:
    """Resets multi-turn session memory for a specific chat or all sessions."""
    chat_id = None
    if request.body:
        try:
            data = json.loads(request.body.decode('utf-8'))
            chat_id = data.get('chat_id')
        except Exception:
            pass
    if not chat_id:
        chat_id = request.POST.get('chat_id') or request.GET.get('chat_id')

    clear_session_memory(request, chat_id=chat_id)

    return JsonResponse({
        "status": f"Session memory {'for ' + chat_id if chat_id else 'all'} reset successfully.",
        "chat_id": chat_id,
        "turn_count": 0
    })


@csrf_exempt
@require_http_methods(["POST"])
def api_upload_document(request: HttpRequest) -> JsonResponse:
    """Uploads, scans (PDF/Image OCR), and dynamically indexes a custom document into the RAG knowledge base."""
    uploaded_file = request.FILES.get('file')
    if not uploaded_file:
        return JsonResponse({"error": "No file uploaded. Please attach a PDF, Word (.docx), Text (.txt, .md), or Image file."}, status=400)

    try:
        file_bytes = uploaded_file.read()
        filename = uploaded_file.name
        content_type = uploaded_file.content_type or ''
        result = RAG_ENGINE.index_custom_document(file_bytes, filename, content_type)
        if not result.get("success"):
            return JsonResponse({"error": result.get("error", "Failed to index document.")}, status=400)

        chat_id = request.POST.get('chat_id')
        if chat_id:
            memory = get_session_memory(request, chat_id=chat_id)
            memory.active_document = result.get("filename", filename)
            save_session_memory(request, memory, chat_id=chat_id)

        return JsonResponse(result)
    except Exception as e:
        logger.error(f"Error in api_upload_document: {e}", exc_info=True)
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_delete_document(request: HttpRequest) -> JsonResponse:
    """Safely deletes a user-uploaded custom document from the knowledge base."""
    filename = ""
    if request.content_type == "application/json" and request.body:
        try:
            data = json.loads(request.body)
            filename = data.get("filename", "")
        except Exception:
            filename = ""
    if not filename:
        filename = request.POST.get("filename", "")

    filename = (filename or "").strip()
    if not filename:
        return JsonResponse({"error": "Filename is required to remove a document."}, status=400)

    try:
        result = RAG_ENGINE.delete_custom_document(filename)
        if not result.get("success"):
            return JsonResponse({"error": result.get("error", "Failed to remove document.")}, status=400)
        return JsonResponse(result)
    except Exception as e:
        logger.error(f"Error in api_delete_document: {e}", exc_info=True)
        return JsonResponse({"error": str(e)}, status=500)


api_chat = api_support_chat


