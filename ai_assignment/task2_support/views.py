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

logger = logging.getLogger(__name__)

# Key & Model performance cache
_EXCLUDED_MODELS = set()
_QUOTA_EXHAUSTED_KEYS = {}

SYSTEM_PROMPT = (
    "You are an expert customer support assistant for a company. "
    "You answer user queries based strictly on the provided retrieved document context.\n\n"
    "Conversation Rules:\n"
    "Memory & Non-Repetition: You have access to the chat history. "
    "Do not repeat information you have already provided in previous turns. "
    "If a user asks a follow-up, build upon your previous answer.\n\n"
    "Topic Switching: If the user changes the topic entirely, acknowledge the switch gracefully "
    "and address the new topic using the new context.\n\n"
    "Mandatory Citations: You MUST cite the specific document section you are drawing from for every factual claim. "
    "Use the format `[Doc: <filename>, Page: <page_number>, Section: <section_title>]` inline or at the end of your sentences.\n\n"
    "Grounding: If the answer is not in the provided context, politely state that you do not have that information. Do not hallucinate."
)


@ensure_csrf_cookie
def chat_ui(request: HttpRequest):
    """Renders the Task 2 Smart Support Assistant UI."""
    history = request.session.get('support_chat_history', [])
    turn_count = len(history) // 2
    active_topic = request.session.get('support_active_topic', 'General Support')

    context = {
        "indexed_chunks_count": (
            RAG_ENGINE._collection.count()
            if RAG_ENGINE._collection and RAG_ENGINE._collection.count() > 0
            else len(RAG_ENGINE._in_memory_chunks)
        ),
        "turn_count": turn_count,
        "active_topic": active_topic,
    }
    return render(request, 'task2_support/index.html', context)


@csrf_exempt
@require_http_methods(["POST"])
def api_support_chat(request: HttpRequest) -> JsonResponse:
    """Multi-turn RAG chat endpoint using Gemini LLM and ChromaDB vector context."""
    try:
        data = json.loads(request.body.decode('utf-8'))
        user_message = data.get('message', '').strip()
    except Exception:
        return JsonResponse({"error": "Invalid JSON payload in request body"}, status=400)

    if not user_message:
        return JsonResponse({"error": "Message cannot be empty"}, status=400)

    # 1. Retrieve session history (tracked up to 10+ turns = 20 messages)
    history: List[Dict[str, str]] = request.session.get('support_chat_history', [])
    topic_history: List[str] = request.session.get('support_topics', [])
    active_topic: Optional[str] = request.session.get('support_active_topic', None)
    delivered_facts: List[str] = request.session.get('support_delivered_facts', [])

    turn_number = (len(history) // 2) + 1

    # 2. Retrieve top-K relevant chunks via ChromaDB RAG
    relevant_chunks = get_relevant_context(user_message, top_k=3)
    formatted_context = format_context(relevant_chunks)

    # 3. Topic Shift Detection
    current_topic = (
        relevant_chunks[0].get("section_title", "Customer Support Policy")
        if relevant_chunks
        else "General Inquiry"
    )
    is_topic_switch = bool(active_topic and active_topic != current_topic)
    returning_to_previous_topic = current_topic in topic_history and is_topic_switch

    # 4. Anti-Repetition Fact Analysis
    new_facts_delivered = []
    already_delivered_count = 0
    if relevant_chunks:
        chunk_lines = relevant_chunks[0].get("text", "").split('\n')
        for line in chunk_lines:
            line_str = line.strip().strip('-*• ')
            if len(line_str) > 15:
                norm_fact = re.sub(r'[^a-zA-Z0-9]', '', line_str.lower()[:50])
                if norm_fact in delivered_facts:
                    already_delivered_count += 1
                else:
                    new_facts_delivered.append(norm_fact)

    primary_citation = relevant_chunks[0].get("citation") if relevant_chunks else "[Doc: Customer_Support_Policy.pdf, Page: 1, Section: § 1. Support]"
    all_citations = [c.get("citation") for c in relevant_chunks if c.get("citation")]

    # 5. Build Augmented Prompt with Anti-Repetition & Topic Switch Directives
    prompt_guidance = []
    if is_topic_switch:
        if returning_to_previous_topic:
            prompt_guidance.append(f"[Directive: The user is returning to a previously discussed topic: '{current_topic}'. Acknowledge the return gracefully.]")
        else:
            prompt_guidance.append(f"[Directive: Topic switch detected from '{active_topic}' to '{current_topic}'. Acknowledge this transition gracefully.]")

    if already_delivered_count > 0:
        prompt_guidance.append(
            "[Directive: The user has previously received core information on this topic in earlier turns. "
            "Do NOT repeat the general baseline boilerplate. Directly answer their specific question with novel details.]"
        )

    guidance_block = ("\n" + "\n".join(prompt_guidance) + "\n") if prompt_guidance else ""
    augmented_user_prompt = (
        f"RETRIEVED DOCUMENT CONTEXT:\n{formatted_context}\n"
        f"{guidance_block}\n"
        f"USER MESSAGE:\n{user_message}"
    )

    # 6. Call LLM (Google Gemini with Multi-Key Pool & Fallback)
    reply_text = call_gemini_chat(
        history=history,
        augmented_user_prompt=augmented_user_prompt,
        user_message=user_message,
        relevant_chunks=relevant_chunks,
        is_topic_switch=is_topic_switch,
        returning_to_previous_topic=returning_to_previous_topic,
        active_topic=active_topic,
        current_topic=current_topic,
        already_delivered_count=already_delivered_count
    )

    # Ensure mandatory citation is present in the final reply
    if primary_citation and primary_citation not in reply_text and "Doc:" not in reply_text:
        reply_text += f"\n\n**Source Reference:** `{primary_citation}`"

    # 7. Update Session State (Maintains up to 10 back-and-forth turns = 20 messages)
    history.append({"role": "user", "content": user_message})
    history.append({"role": "model", "content": reply_text})

    # Keep only the last 20 messages (10 turns)
    if len(history) > 20:
        history = history[-20:]

    if current_topic not in topic_history:
        topic_history.append(current_topic)

    delivered_facts.extend(new_facts_delivered)

    request.session['support_chat_history'] = history
    request.session['support_topics'] = topic_history
    request.session['support_active_topic'] = current_topic
    request.session['support_delivered_facts'] = delivered_facts
    request.session.modified = True

    sources = []
    for chunk in relevant_chunks[:3]:
        excerpt = (chunk.get("text") or "").strip().replace("\n", " ")
        if len(excerpt) > 280:
            excerpt = excerpt[:277] + "…"
        sources.append({
            "citation": chunk.get("citation") or "",
            "excerpt": excerpt,
        })

    return JsonResponse({
        "reply": reply_text,
        "citation": primary_citation,
        "citations": all_citations,
        "sources": sources,
        "topic": current_topic,
        "previous_topic": active_topic if is_topic_switch else None,
        "topics": topic_history,
        "anti_repeat": already_delivered_count > 0,
        "is_topic_switch": is_topic_switch,
        "returning_to_previous_topic": returning_to_previous_topic,
        "turn_number": turn_number,
        "total_turns": len(history) // 2
    })


def call_gemini_chat(
    history: List[Dict[str, str]],
    augmented_user_prompt: str,
    user_message: str,
    relevant_chunks: List[Dict[str, Any]],
    is_topic_switch: bool,
    returning_to_previous_topic: bool,
    active_topic: Optional[str],
    current_topic: str,
    already_delivered_count: int
) -> str:
    """Executes multi-turn conversation using google-generativeai SDK with automatic failover."""
    keys_pool = getattr(settings, 'GEMINI_API_KEYS', [])
    single_key = getattr(settings, 'GEMINI_API_KEY', '')
    if single_key and single_key not in keys_pool:
        keys_pool = [single_key] + keys_pool

    # Models priority: gemini-1.5-flash as requested, falling back to active 2026 endpoints
    candidate_models = ['gemini-1.5-flash', 'gemini-flash-latest', 'gemini-2.5-flash', 'gemini-3.8-flash']

    try:
        import google.generativeai as genai

        # Prepare formatted history for Gemini start_chat
        # google-generativeai requires: [{"role": "user"|"model", "parts": [...]}]
        chat_history_payload = []
        for msg in history[-18:]:  # leave room for current turn
            role = "user" if msg.get("role") == "user" else "model"
            chat_history_payload.append({
                "role": role,
                "parts": [msg.get("content", "")]
            })

        import time
        now = time.time()
        active_keys = [k for k in keys_pool if k and (_QUOTA_EXHAUSTED_KEYS.get(k, 0) + 300 < now)]

        for key_candidate in active_keys:
            genai.configure(api_key=key_candidate)

            for model_name in candidate_models:
                if model_name in _EXCLUDED_MODELS:
                    continue
                try:
                    model = genai.GenerativeModel(
                        model_name=model_name,
                        system_instruction=SYSTEM_PROMPT
                    )
                    chat = model.start_chat(history=chat_history_payload)
                    response = chat.send_message(augmented_user_prompt)
                    if response and response.text:
                        return response.text.strip()
                except Exception as model_err:
                    err_str = str(model_err)
                    # If 404, mark model globally so we don't retry it on every key
                    if "404" in err_str:
                        _EXCLUDED_MODELS.add(model_name)
                        continue
                    # If quota reached, remember key cooldown and advance to next key
                    elif "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                        _QUOTA_EXHAUSTED_KEYS[key_candidate] = time.time()
                        break
                    else:
                        continue
    except Exception as general_err:
        logger.error(f"Failed invoking Gemini: {general_err}")

    # High-fidelity deterministic fallback guaranteeing context, anti-repetition & citations
    return synthesize_deterministic_support_reply(
        user_message=user_message,
        relevant_chunks=relevant_chunks,
        is_topic_switch=is_topic_switch,
        returning_to_previous_topic=returning_to_previous_topic,
        active_topic=active_topic,
        current_topic=current_topic,
        already_delivered_count=already_delivered_count
    )


def synthesize_deterministic_support_reply(
    user_message: str,
    relevant_chunks: List[Dict[str, Any]],
    is_topic_switch: bool,
    returning_to_previous_topic: bool,
    active_topic: Optional[str],
    current_topic: str,
    already_delivered_count: int
) -> str:
    """Deterministic conversational synthesis when external LLM APIs are offline or rate-limited."""
    reply_parts = []

    # 1. Topic Transition / Continuity Bridge
    if is_topic_switch:
        if returning_to_previous_topic:
            reply_parts.append(f"*Returning to our earlier discussion regarding **{current_topic}**:*\n\n")
        else:
            prev_name = active_topic or "our previous inquiry"
            reply_parts.append(f"*Acknowledging the topic switch from **{prev_name}** to **{current_topic}**:*\n\n")

    # 2. Anti-Repetition Acknowledgment
    if already_delivered_count > 0:
        reply_parts.append(
            "> **Note:** *As discussed earlier in this session, you have already received the baseline policy for this topic. "
            "(Avoiding repeating previously delivered rules).* Here are the specific points addressing your inquiry:\n\n"
        )

    # 3. Targeted Policy Facts
    if relevant_chunks:
        top_chunk = relevant_chunks[0]
        text_content = top_chunk.get("text", "")
        citation = top_chunk.get("citation", "")

        # Find most relevant sentences/lines matching query
        q_words = [w for w in re.findall(r'\b\w+\b', user_message.lower()) if len(w) > 3 and w not in STOP_WORDS]
        matching_lines = []

        for line in text_content.split('\n'):
            line_str = line.strip()
            if not line_str or line_str.startswith('#'):
                continue
            score = sum(1 for w in q_words if w in line_str.lower())
            if score > 0:
                matching_lines.append((score, line_str))

        if matching_lines:
            matching_lines.sort(key=lambda x: x[0], reverse=True)
            chosen_body = "\n\n".join(item[1] for item in matching_lines[:3])
            reply_parts.append(chosen_body)
        else:
            # First 2 non-header paragraphs
            paragraphs = [p.strip() for p in text_content.split('\n\n') if p.strip() and not p.startswith('#')]
            reply_parts.append("\n\n".join(paragraphs[:2]) if paragraphs else text_content[:300])

        # 4. Mandatory Section Citation
        reply_parts.append(f"\n\n**Official Citation:** `{citation}`")
    else:
        reply_parts.append("I do not have specific documented policies matching this query in the provided knowledge base.")

    return "".join(reply_parts)


@csrf_exempt
@require_http_methods(["POST"])
def api_reset(request: HttpRequest) -> JsonResponse:
    """Resets the multi-turn session memory."""
    for key in ['support_chat_history', 'support_topics', 'support_active_topic', 'support_delivered_facts']:
        if key in request.session:
            del request.session[key]
    request.session.modified = True
    return JsonResponse({
        "status": "Session reset successfully.",
        "turn_count": 0
    })


api_chat = api_support_chat
