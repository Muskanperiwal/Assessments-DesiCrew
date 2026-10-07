import os
import json
from pipeline import DocumentPipeline

def evaluate_pipeline():
    pipeline = DocumentPipeline("question_3_document_pipeline/ground_truth.json")
    results = pipeline.run_pipeline()

    # Save deliverables
    outputs_dir = "question_3_document_pipeline/outputs"
    os.makedirs(outputs_dir, exist_ok=True)

    extractions_path = os.path.join(outputs_dir, "extractions.json")
    flagging_path = os.path.join(outputs_dir, "flagging_report.json")

    with open(extractions_path, "w", encoding="utf-8") as f:
        json.dump(results["documents"], f, indent=2)

    with open(flagging_path, "w", encoding="utf-8") as f:
        json.dump(results["flagging_report"], f, indent=2)

    # Evaluate against ground truth
    gt = pipeline.ground_truth
    total_fields = 0
    correct_fields = 0
    printed_total = 0
    printed_correct = 0
    handwritten_total = 0
    handwritten_correct = 0

    print("=" * 85)
    print("📋 QUESTION 3: PIPELINE ACCURACY EVALUATION (AGAINST GROUND TRUTH)")
    print("=" * 85)
    print(f"{'Document Filename':<35} | {'Type':<28} | {'Field':<25} | {'Score':<6} | {'Status'}")
    print("-" * 85)

    for filename, doc_data in results["documents"].items():
        gt_doc = gt.get(filename, {})
        gt_fields = gt_doc.get("fields", {})
        is_hw = doc_data["is_handwritten"]

        for field_name, field_info in doc_data["extracted_fields"].items():
            total_fields += 1
            if is_hw:
                handwritten_total += 1
            else:
                printed_total += 1

            extracted_val = str(field_info["value"]).strip().lower()
            gt_val = str(gt_fields.get(field_name, "")).strip().lower()

            # Normalize for comparison
            match = (extracted_val == gt_val) or (extracted_val in gt_val) or (gt_val in extracted_val)
            if match:
                correct_fields += 1
                status = "✅ MATCH"
                if is_hw:
                    handwritten_correct += 1
                else:
                    printed_correct += 1
            else:
                status = "❌ MISMATCH"

            flag_marker = " [FLAGGED]" if field_info["confidence"] < 0.85 else ""
            print(f"{filename[:33]:<35} | {doc_data['document_type'][:26]:<28} | {field_name[:23]:<25} | {field_info['confidence']:.2f}   | {status}{flag_marker}")

    accuracy = (correct_fields / total_fields) * 100 if total_fields else 0
    printed_acc = (printed_correct / printed_total) * 100 if printed_total else 0
    hw_acc = (handwritten_correct / handwritten_total) * 100 if handwritten_total else 0

    print("=" * 85)
    print(f"📊 SUMMARY ACCURACY REPORT:")
    print(f"   • Overall Field Accuracy:       {correct_fields}/{total_fields} ({accuracy:.2f}%)")
    print(f"   • Printed Fields Accuracy:      {printed_correct}/{printed_total} ({printed_acc:.2f}%)")
    print(f"   • Handwritten Fields Accuracy:  {handwritten_correct}/{handwritten_total} ({hw_acc:.2f}%)")
    print(f"   • Total Fields Flagged (<0.85): {results['flagging_report']['total_flagged_fields']} (routed to Human Review)")
    print(f"   • Deliverable Files Saved:")
    print(f"       - Extractions:   {extractions_path}")
    print(f"       - Flagging Rep:  {flagging_path}")
    print("=" * 85)

if __name__ == '__main__':
    evaluate_pipeline()
