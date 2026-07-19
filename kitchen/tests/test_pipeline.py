import unittest

from kitchen.canonicalize import extract_github_repos
from kitchen.dedup import normalize_text, get_shingles
from datasketch import MinHash
from kitchen.rank import score_skill, ecosystem_match
from kitchen.emit import resolve_install_command, get_vendor

class TestPipeline(unittest.TestCase):
    
    # 1. Canonicalize Tests
    def test_extract_github_repos(self):
        readme = """
        Check out these repositories:
        - [Skill 1](https://github.com/org1/repo1)
        - [Skill 2](https://github.com/org2/repo2/tree/main/skills/subpath)
        - Exclude badge link: https://github.com/awesome-re/badge.svg
        - Exclude attachments: https://github.com/user-attachments/assets/abc
        """
        repos = extract_github_repos(readme)
        self.assertEqual(len(repos), 2)
        self.assertEqual(repos[0]["org"], "org1")
        self.assertEqual(repos[0]["repo"], "repo1")
        self.assertEqual(repos[0]["path"], "")
        
        self.assertEqual(repos[1]["org"], "org2")
        self.assertEqual(repos[1]["repo"], "repo2")
        self.assertEqual(repos[1]["path"], "skills/subpath")

    # 2. Dedup Tests
    def test_dedup_jaccard(self):
        doc1 = "The quick brown fox jumps over the lazy dog"
        doc2 = "The quick brown fox jumps over the lazy dog."
        doc3 = "A completely different sentence about birds"
        
        shingles1 = get_shingles(normalize_text(doc1), k=3)
        shingles2 = get_shingles(normalize_text(doc2), k=3)
        shingles3 = get_shingles(normalize_text(doc3), k=3)
        
        m1 = MinHash(num_perm=64)
        m2 = MinHash(num_perm=64)
        m3 = MinHash(num_perm=64)
        
        for s in shingles1: m1.update(s.encode("utf-8"))
        for s in shingles2: m2.update(s.encode("utf-8"))
        for s in shingles3: m3.update(s.encode("utf-8"))
        
        self.assertGreaterEqual(m1.jaccard(m2), 0.7)
        self.assertLess(m1.jaccard(m3), 0.3)

    # 3. Rank Tests
    def test_rank_scoring(self):
        # Invariant: human-read > official-unread
        skill_human_read = {
            "tier": "core",
            "reviewed_by": "John Doe",
            "provenance": "community",
            "license": "MIT",
            "upstream": {"fetched_at": "2026-07-01T00:00:00Z"},
            "native_ecosystem": "generic"
        }
        
        skill_official_unread = {
            "tier": "shell",
            "reviewed_by": None,
            "provenance": "official",
            "license": "Apache-2.0",
            "upstream": {"fetched_at": "2026-07-01T00:00:00Z"},
            "native_ecosystem": "generic"
        }
        
        score_hr = score_skill(skill_human_read)
        score_ou = score_skill(skill_official_unread)
        
        self.assertGreater(score_hr, score_ou)
        self.assertGreaterEqual(score_hr, 1000)

    # 4. Tool Match
    def test_ecosystem_match(self):
        self.assertTrue(ecosystem_match("claude", "claude-code"))
        self.assertTrue(ecosystem_match("google", "antigravity"))
        self.assertFalse(ecosystem_match("vscode", "claude-code"))

    # 5. Emit golden resolver
    def test_resolve_install_command(self):
        skill = {
            "name": "my-skill",
            "origin": {
                "org": "my-org",
                "repo": "my-repo",
                "path": "skills/my-skill",
                "default_branch": "main"
            },
            "install_hints": {
                "claude-code": {
                    "plugin_name": "custom-plugin",
                    "marketplace": "custom-market"
                }
            }
        }
        
        methods_dict = {
            ("claude-code", "plugin"): {
                "template": "/plugin marketplace add {org}/{repo}\n/plugin install {plugin_name}@{marketplace}",
                "requires_hints": ["plugin_name", "marketplace"]
            },
            ("claude-code", "manual"): {
                "template": "Copy files to ~/.claude/skills/{skill_name}",
                "requires_hints": []
            }
        }
        
        # Test plugin resolves using hints
        cmd = resolve_install_command(skill, "claude-code", methods_dict, ["plugin", "manual"])
        self.assertIn("/plugin install custom-plugin@custom-market", cmd)
        
        # Test fallback to manual if hints missing
        skill_no_hints = skill.copy()
        skill_no_hints["install_hints"] = {}
        cmd_fallback = resolve_install_command(skill_no_hints, "claude-code", methods_dict, ["plugin", "manual"])
        self.assertEqual(cmd_fallback, "Copy files to ~/.claude/skills/my-skill")

    # 6. Vendor resolution
    def test_vendor(self):
        source_vendor = {"anthropic-official": "anthropic", "google-official": "google"}
        self.assertEqual(get_vendor("anthropic-official", source_vendor), "anthropic")
        self.assertEqual(get_vendor("google-official", source_vendor), "google")
        self.assertIsNone(get_vendor("angular-source", source_vendor))

if __name__ == "__main__":
    unittest.main()
