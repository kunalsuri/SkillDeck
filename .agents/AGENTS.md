# Workspace-Specific Custom Rules

## Environment Setup and Dependencies
- **Keep Setup Scripts in Sync**: Always keep `scripts/win/dev-setup.ps1` and `scripts/linux/dev-setup.sh` strictly in sync. Any Python dependency (e.g. `pytest`) or frontend dependency validation tools (e.g. Playwright browsers via `npx playwright install`) added to one must also be added to the other.
- **Do Not Auto-Install Runtimes**: If Python or Node.js is missing from the user's system, **never** attempt to install them automatically.
- **Cognitive Overload Reduction**: When runtimes (Python, Node.js) are missing, notify the user immediately with a clear explanation of what is missing, why it is required for the repository, and provide simple step-by-step guidance on how they can install it, rather than taking complex or potentially invasive actions on their system.
