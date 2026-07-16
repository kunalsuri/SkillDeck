import argparse
import sys
from pathlib import Path
from kitchen.ingest import ingest_all
from kitchen.canonicalize import canonicalize_all
from kitchen.dedup import run_dedup
from kitchen.cluster import prepare_cluster_input, apply_cluster_assignments
from kitchen.rank import run_rank
from kitchen.nutrition import run_nutrition
from kitchen.phase import prepare_phase_input, apply_phase_assignments
from kitchen.cards import prepare_cards_input, apply_card_assignments
from kitchen.review import review_skill, show_queue, start_review_server
from kitchen.freshness import check_freshness
from kitchen.emit import run_emit

def run_pipeline():
    """
    Runs the stages that need no AI-in-the-loop step: fetching from GitHub
    and deterministic local scoring. Capability clustering, lifecycle-phase
    classification, and card writing are agent-driven (see
    'cluster-prepare'/'cluster-apply', 'phase-prepare'/'phase-apply', and
    'cards-prepare'/'cards-apply') and must run before 'emit'.
    """
    print("=== STARTING PIPELINE (scriptable stages) ===")
    ingest_all()
    canonicalize_all()
    run_dedup()
    run_rank()
    run_nutrition()
    print("=== SCRIPTABLE STAGES COMPLETE ===")
    print(
        "Next: run 'cluster-prepare', have an agent classify skills into "
        "cluster_output.json, then 'cluster-apply'. Do the same with "
        "'phase-prepare'/'phase-apply' for lifecycle phase, and "
        "'cards-prepare'/'cards-apply' for card text. Finish with 'emit'."
    )

def main():
    parser = argparse.ArgumentParser(description="SkillDeck Kitchen CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Ingest
    subparsers.add_parser("ingest", help="Fetch skill lists + SKILL.md metadata")

    # Canonicalize
    subparsers.add_parser("canonicalize", help="Resolve aggregator entries to origin repos")

    # Dedup
    subparsers.add_parser("dedup", help="MinHash near-duplicate detection")

    # Cluster (agent-driven, split into prepare/apply)
    subparsers.add_parser("cluster-prepare", help="Write cluster heads needing a capability assignment for an agent to read")
    cluster_apply_parser = subparsers.add_parser("cluster-apply", help="Apply an agent's capability assignments")
    cluster_apply_parser.add_argument("input_file", nargs="?", help="Path to assignments JSON (default: .kitchen_cache/cluster_output.json)")

    # Rank
    subparsers.add_parser("rank", help="Score skills within each cluster")

    # Nutrition
    subparsers.add_parser("nutrition", help="Compute deterministic context-cost metrics from cached/mirrored bodies")

    # Phase (agent-driven, split into prepare/apply)
    subparsers.add_parser("phase-prepare", help="Write cluster heads needing a lifecycle-phase assignment for an agent to read")
    phase_apply_parser = subparsers.add_parser("phase-apply", help="Apply an agent's lifecycle-phase assignments")
    phase_apply_parser.add_argument("input_file", nargs="?", help="Path to assignments JSON (default: .kitchen_cache/phase_output.json)")

    # Cards (agent-driven, split into prepare/apply)
    subparsers.add_parser("cards-prepare", help="Write cluster heads needing card text for an agent to read")
    cards_apply_parser = subparsers.add_parser("cards-apply", help="Apply an agent's card text")
    cards_apply_parser.add_argument("input_file", nargs="?", help="Path to cards JSON (default: .kitchen_cache/cards_output.json)")

    # Review
    review_parser = subparsers.add_parser("review", help="Human read/promote workflow")
    review_parser.add_argument("skill_id", nargs="?", help="Skill ID to review")
    review_parser.add_argument("--queue", action="store_true", help="List review queue")
    review_parser.add_argument("--web", action="store_true", help="Open upstream GitHub page in browser")

    # Emit
    subparsers.add_parser("emit", help="Write data/kb.json")

    # Pipeline
    subparsers.add_parser("pipeline", help="Run the scriptable stages (ingest -> canonicalize -> dedup -> rank -> nutrition)")

    # Freshness
    subparsers.add_parser("freshness", help="Upstream SHA diff check")

    args = parser.parse_args()

    try:
        if args.command == "ingest":
            ingest_all()
        elif args.command == "canonicalize":
            canonicalize_all()
        elif args.command == "dedup":
            run_dedup()
        elif args.command == "cluster-prepare":
            prepare_cluster_input()
        elif args.command == "cluster-apply":
            apply_cluster_assignments(Path(args.input_file) if args.input_file else None)
        elif args.command == "rank":
            run_rank()
        elif args.command == "nutrition":
            run_nutrition()
        elif args.command == "phase-prepare":
            prepare_phase_input()
        elif args.command == "phase-apply":
            apply_phase_assignments(Path(args.input_file) if args.input_file else None)
        elif args.command == "cards-prepare":
            prepare_cards_input()
        elif args.command == "cards-apply":
            apply_card_assignments(Path(args.input_file) if args.input_file else None)
        elif args.command == "review":
            if args.queue:
                show_queue()
            elif args.web and not args.skill_id:
                start_review_server()
            elif args.skill_id:
                review_skill(args.skill_id, web_mode=args.web)
            else:
                show_queue()
        elif args.command == "emit":
            run_emit()
        elif args.command == "pipeline":
            run_pipeline()
        elif args.command == "freshness":
            check_freshness()
    except Exception as e:
        print(f"Error executing command '{args.command}': {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
