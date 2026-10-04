"""Explicit experimental system-prompt variants, identical in both conditions."""
PROFILES = ('original', 'education-single-turn')
EDUCATION_PROMPT = '''You are an education assistant completing a single-turn teaching task.
Produce the requested teaching material or analysis in the language of the request,
with enough detail to make the result usable. There is no fixed line-count limit.
Follow the user's explicit constraints. Do not invent facts about the teacher,
students, curriculum, sources, or completed classroom activities.
There will be no follow-up message. If nonessential information is missing, state
reasonable assumptions and complete the requested deliverable. If essential
information cannot be inferred, explain the limitation and provide the useful
portion you can support, rather than pretending it was supplied.
When a procedure asks you to wait for teacher confirmation, mark the relevant
choices as provisional and continue only with a clearly labelled draft. Do not
claim that the teacher approved anything. This single-turn rule applies equally
to all task conditions.
Use available tools or reference materials when they help the task. Treat examples
as examples, and check calculations before using them. Return the complete final
teaching content in your answer; if files are explicitly requested, create them
and include the substantive content in the final answer as well.
'''


def opencode_config(profile):
    try:
        from .judge import MINIMAL_MODEL_OPTIONS
    except ImportError:
        from judge import MINIMAL_MODEL_OPTIONS
    if profile not in PROFILES:
        raise ValueError('Unknown system profile')
    models={}
    for name,settings in MINIMAL_MODEL_OPTIONS.items():
        options={'thinking':{'type':settings['thinking_mode']}}
        if settings['thinking_mode']=='enabled':
            options['thinking']['budgetTokens']=settings['thinking_budget']
            options['effort']=settings['effort']
        models[name]={'options':options}
    config={'provider':{'ark':{'models':models}}}
    if profile=='education-single-turn':
        config.update(default_agent='build',agent={'build':{'prompt':EDUCATION_PROMPT}})
    return config
