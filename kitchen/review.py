import json
import os
import subprocess
import tempfile
import sys
import http.server
import urllib.parse
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from kitchen.config import SKILLS_JSON, CACHE_DIR, KB_JSON, PROJECT_ROOT
from kitchen.utils import parse_skill_md, load_all_skills, save_skills, atomic_write_json
from kitchen.dedup import get_skill_body
from kitchen.cards import load_cards_cache, save_cards_cache

def get_git_username() -> str:
    try:
        username = subprocess.check_output(
            ["git", "config", "user.name"], 
            stderr=subprocess.DEVNULL
        ).decode("utf-8").strip()
        if username:
            return username
    except Exception:
        pass
    return os.getenv("USERNAME") or os.getenv("USER") or "Maintainer"

def run_editor(content: str, suffix: str = ".json") -> str:
    editor = os.getenv("EDITOR")
    if not editor:
        if sys.platform == "win32":
            editor = "notepad.exe"
        else:
            editor = "vi"
            
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False, mode="w", encoding="utf-8") as temp:
        temp.write(content)
        temp_path = temp.name
        
    try:
        subprocess.run([editor, temp_path], check=True)
        with open(temp_path, "r", encoding="utf-8") as f:
            return f.read()
    finally:
        try:
            os.unlink(temp_path)
        except Exception:
            pass

def print_skill_details(skill: dict):
    print("=" * 80)
    print(f"SKILL ID: {skill['id']}")
    print(f"Name: {skill['name']}")
    print(f"Provenance: {skill['provenance']}")
    print(f"License: {skill['license']} (Mirrorable: {skill['mirrorable']})")
    print(f"Tier: {skill['tier']}")
    print(f"Origin Path: github.com/{skill['origin']['org']}/{skill['origin']['repo']}/{skill['origin']['path']}")
    print("-" * 80)
    print(f"Frontmatter Description:\n{skill.get('frontmatter_description')}")
    print("-" * 80)
    # Excerpt body
    body = get_skill_body(skill)
    lines = body.splitlines()
    print("Body Excerpt (first 10 lines):")
    for line in lines[:10]:
        print(f"  {line}")
    if len(lines) > 10:
        print("  ...")
    print("=" * 80)

def edit_card_workflow(skill_id: str, blob_sha: str, cards_cache: dict) -> dict:
    cache_key = f"{skill_id}:{blob_sha}"
    card = cards_cache.get(cache_key) or {
        "title": "",
        "what_it_does": "",
        "try_saying": ""
    }
    
    # We edit the JSON
    card_editable = {
        "title": card.get("title", ""),
        "what_it_does": card.get("what_it_does", ""),
        "try_saying": card.get("try_saying", "")
    }
    
    card_str = json.dumps(card_editable, indent=2, ensure_ascii=False)
    print("Opening editor to modify card JSON...")
    
    try:
        modified_str = run_editor(card_str, ".json")
        modified_card = json.loads(modified_str)
        
        # Merge back
        card.update(modified_card)
        card["generated_by"] = "human"
        card["generated_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        
        cards_cache[cache_key] = card
        save_cards_cache(cards_cache)
        print("Card updated successfully in cache.")
        return card
    except Exception as e:
        print(f"Error editing card JSON: {e}")
        return card

def review_skill(skill_id: str, web_mode: bool = False):
    skill_lookup = load_all_skills(SKILLS_JSON)
    
    if skill_id not in skill_lookup:
        print(f"Skill '{skill_id}' not found.")
        return
        
    skill = skill_lookup[skill_id]
    
    if web_mode:
        org = skill["origin"]["org"]
        repo = skill["origin"]["repo"]
        branch = skill["origin"]["default_branch"]
        path = skill["origin"]["path"]
        url = f"https://github.com/{org}/{repo}/blob/{branch}/{path}/SKILL.md"
        print(f"Opening browser link: {url}")
        import webbrowser
        webbrowser.open(url)
        return

    print_skill_details(skill)
    cards_cache = load_cards_cache()
    cache_key = f"{skill['id']}:{skill['upstream']['blob_sha']}"
    card = cards_cache.get(cache_key)
    if card:
        print("Generated Explainer Card:")
        print(f"  Title: {card.get('title')}")
        print(f"  What it does: {card.get('what_it_does')}")
        print(f"  Try saying: \"{card.get('try_saying')}\"")
        print(f"  Source: {card.get('generated_by')} (at {card.get('generated_at')})")
    else:
        print("No card generated yet (run 'python -m kitchen cards' or choose 'edit card' to write one manually).")
    print("-" * 80)
    
    git_user = get_git_username()
    
    while True:
        choice = input("[p]romote  [e]dit card  [r]eject  [s]kip: ").strip().lower()
        if choice == 'p':
            skill["tier"] = "core"
            skill["reviewed_by"] = git_user
            skill["reviewed_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            skill["reviewed_commit_sha"] = skill["upstream"]["commit_sha"]
            skill["reject_reason"] = None
            
            # Save
            save_skills(SKILLS_JSON, list(skill_lookup.values()))
            print(f"Skill '{skill_id}' successfully promoted to core.")
            break
        elif choice == 'e':
            card = edit_card_workflow(skill["id"], skill["upstream"]["blob_sha"], cards_cache)
            print("Generated Explainer Card updated:")
            print(f"  Title: {card.get('title')}")
            print(f"  What it does: {card.get('what_it_does')}")
            print(f"  Try saying: \"{card.get('try_saying')}\"")
            print(f"  Source: {card.get('generated_by')}")
            print("-" * 80)
        elif choice == 'r':
            reason = input("Enter reject reason: ").strip()
            skill["tier"] = "rejected"
            skill["reject_reason"] = reason
            
            # Save
            save_skills(SKILLS_JSON, list(skill_lookup.values()))
            print(f"Skill '{skill_id}' rejected with reason: {reason}")
            break
        elif choice == 's':
            print("Skipped.")
            break
        else:
            print("Invalid option.")

def show_queue():
    skills_map = load_all_skills(SKILLS_JSON)
    skills = list(skills_map.values())
    active_skills = [s for s in skills if s.get("status") == "active" and s.get("tier") == "shell"]
    
    if not active_skills:
        print("No skills in the review queue (all are promoted/rejected, or no skills ingested).")
        return

    # Count cluster sizes
    cluster_counts = {}
    for s in skills:
        if s.get("status") == "active":
            cid = s.get("cluster_id")
            if cid:
                cluster_counts[cid] = cluster_counts.get(cid, 0) + 1

    # Filter to cluster heads only (meaning highest ranked in its cluster)
    cluster_groups = {}
    for s in active_skills:
        cid = s.get("cluster_id")
        if cid:
            cluster_groups.setdefault(cid, []).append(s)
            
    # Sort key helper
    from kitchen.rank import score_skill
    
    heads = []
    for cid, members in cluster_groups.items():
        sorted_members = sorted(members, key=lambda m: (-m.get("score_default", score_skill(m)), m["id"]))
        heads.append(sorted_members[0])
        
    # Queue ordering:
    # 1. Cluster size descending
    # 2. Provenance score: official (3) > partner (2) > community (1)
    # 3. ID alphabetical
    def queue_sort_key(s):
        cid = s.get("cluster_id")
        c_size = cluster_counts.get(cid, 1)
        prov_score = {"official": 3, "partner": 2, "community": 1}.get(s["provenance"], 1)
        return (-c_size, -prov_score, s["id"])
        
    sorted_queue = sorted(heads, key=queue_sort_key)
    
    print("=" * 80)
    print("REVIEW QUEUE (shell cluster heads):")
    print(f"{'Skill ID':<40} | {'Cluster Size':<12} | {'Provenance':<12}")
    print("-" * 80)
    for head in sorted_queue:
        cid = head.get("cluster_id")
        size = cluster_counts.get(cid, 1)
        print(f"{head['id']:<40} | {size:<12} | {head['provenance']:<12}")
    print("=" * 80)
    print("To review a skill, run: python -m kitchen review <skill_id>")


class ReviewRequestHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        sys.stdout.write(f"{self.address_string()} - - [{self.log_date_time_string()}] {format % args}\n")

    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        if path in ("/", "/audit.html", "/index.html"):
            html_path = PROJECT_ROOT / "audit" / "audit.html"
            if not html_path.exists():
                self.send_error(404, f"File not found: {html_path}")
                return
            try:
                with open(html_path, "r", encoding="utf-8") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(content.encode("utf-8"))
            except Exception as e:
                self.send_error(500, f"Error reading page: {e}")
            return

        elif path == "/api/config":
            try:
                from kitchen.config import CAPABILITIES, TOOLS
                config_data = {
                    "git_username": get_git_username(),
                    "capabilities": CAPABILITIES,
                    "tools": TOOLS
                }
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps(config_data).encode("utf-8"))
            except Exception as e:
                self.send_error(500, f"Error: {e}")
            return

        elif path == "/api/skills":
            try:
                skills_map = load_all_skills(SKILLS_JSON)
                skills_list = list(skills_map.values())
                
                # Fetch body content for each skill
                for skill in skills_list:
                    try:
                        skill["body"] = get_skill_body(skill)
                    except Exception:
                        skill["body"] = ""
                
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps(skills_list).encode("utf-8"))
            except Exception as e:
                self.send_error(500, f"Error loading skills: {e}")
            return

        elif path == "/api/cards":
            try:
                cards = load_cards_cache()
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps(cards).encode("utf-8"))
            except Exception as e:
                self.send_error(500, f"Error loading cards: {e}")
            return

        else:
            self.send_error(404, "Not Found")

    def do_POST(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        if path == "/api/save":
            try:
                content_length = int(self.headers.get('Content-Length', 0))
                post_data = self.rfile.read(content_length)
                payload = json.loads(post_data.decode("utf-8"))

                skills = payload.get("skills")
                cards = payload.get("cards")

                if skills is not None:
                    save_skills(SKILLS_JSON, skills)
                if cards is not None:
                    save_cards_cache(cards)
                
                # Re-emit final data/kb.json
                from kitchen.emit import run_emit
                run_emit()

                response = {"success": True}
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps(response).encode("utf-8"))
            except Exception as e:
                self.send_error(500, f"Error saving data: {e}")
            return
        else:
            self.send_error(404, "Not Found")


def start_review_server(port: int = 8000):
    for attempt in range(10):
        try:
            httpd = http.server.HTTPServer(('127.0.0.1', port), ReviewRequestHandler)
            break
        except OSError:
            port += 1
    else:
        print("Error: Could not find an available port to start the server.")
        return

    print("=" * 80)
    print(f"SkillDeck Review Dashboard Server running at http://127.0.0.1:{port}/")
    print("Press Ctrl+C to stop the server.")
    print("=" * 80)
    
    webbrowser.open(f"http://127.0.0.1:{port}/")
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping review server.")
        httpd.server_close()
