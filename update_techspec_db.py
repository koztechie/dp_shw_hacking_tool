from src.analyzer.prompt_manager import prompt_manager

# Get the updated builtin prompt
builtin_template = prompt_manager._get_builtin_prompt("techspec_generator")

# Variables required
expected_vars = [
    "idea_json", "hackathon_title", "hardware_constraints", 
    "constraints_text", "realtime_news", "schema_json"
]

# Create a new version in DB, which makes it the active one
prompt_manager.create_prompt_version("techspec_generator", builtin_template, variables=expected_vars)

print("DB prompt updated.")
