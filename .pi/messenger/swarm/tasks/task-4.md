# Dependency file creation + reliability review — Hledac universal

Safe dependency and audit workflow for /Users/vojtechhamada/PycharmProjects/Hledac/hledac/universal scope:
1. Find all imports in this scope
2. Determine correct dependency file target (requirements.txt already exists)
3. Create evidence-based dependency list
4. Verify consistency with actual imports
5. Ensure no files outside scope are touched
