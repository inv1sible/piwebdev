from django import forms
from .models import Project, ProjectMemory, ProjectPiSettings, UserPiSettings

PROVIDER_CHOICES = [
    ("", "— select provider —"),
    ("anthropic", "Anthropic"),
    ("openai", "OpenAI"),
    ("openai-codex", "OpenAI Codex"),
    ("gemini", "Gemini"),
    ("bedrock", "AWS Bedrock"),
    ("vertex", "Google Vertex"),
]

MODEL_CHOICES = [
    ("", "— select model —"),
    # Anthropic
    ("claude-opus-4-7", "Claude Opus 4.7"),
    ("claude-sonnet-4-6", "Claude Sonnet 4.6"),
    ("claude-haiku-4-5-20251001", "Claude Haiku 4.5"),
    ("claude-3-7-sonnet-20250219", "Claude 3.7 Sonnet"),
    ("claude-3-5-haiku-20241022", "Claude 3.5 Haiku"),
    # OpenAI
    ("gpt-5.5", "GPT-5.5"),
    ("gpt-4o", "GPT-4o"),
    ("gpt-4o-mini", "GPT-4o Mini"),
    ("o3", "o3"),
    ("o4-mini", "o4-mini"),
    ("codex-mini-latest", "Codex Mini"),
    # Gemini
    ("gemini-2.5-pro", "Gemini 2.5 Pro"),
    ("gemini-2.5-flash", "Gemini 2.5 Flash"),
]

THINKING_CHOICES = [
    ("", "— select thinking level —"),
    ("none", "None"),
    ("minimal", "Minimal"),
    ("low", "Low"),
    ("medium", "Medium"),
    ("high", "High"),
    ("auto", "Auto"),
]

PROJECT_PROVIDER_CHOICES = [("", "— use general setting —")] + PROVIDER_CHOICES[1:]
PROJECT_MODEL_CHOICES = [("", "— use general setting —")] + MODEL_CHOICES[1:]
PROJECT_THINKING_CHOICES = [("", "— use general setting —")] + THINKING_CHOICES[1:]


class ProjectCreateForm(forms.Form):
    name = forms.CharField(max_length=120)
    init_git = forms.BooleanField(required=False, initial=True)
    add_readme = forms.BooleanField(required=False, initial=True)


class ProjectRenameForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ["name"]


class ProjectMemoryForm(forms.ModelForm):
    class Meta:
        model = ProjectMemory
        fields = ["content"]
        widgets = {"content": forms.Textarea(attrs={"rows": 18})}


class ProjectPiSettingsForm(forms.ModelForm):
    provider = forms.ChoiceField(choices=PROJECT_PROVIDER_CHOICES, required=False)
    model = forms.ChoiceField(choices=PROJECT_MODEL_CHOICES, required=False)
    thinking_level = forms.ChoiceField(choices=PROJECT_THINKING_CHOICES, required=False)

    class Meta:
        model = ProjectPiSettings
        fields = ["provider", "model", "thinking_level", "mindset", "inject_memory", "extra_args"]
        widgets = {"mindset": forms.Textarea(attrs={"rows": 5})}


class UserPiSettingsForm(forms.ModelForm):
    provider = forms.ChoiceField(choices=PROVIDER_CHOICES, required=False)
    model = forms.ChoiceField(choices=MODEL_CHOICES, required=False)
    thinking_level = forms.ChoiceField(choices=THINKING_CHOICES, required=False)

    class Meta:
        model = UserPiSettings
        fields = ["provider", "model", "thinking_level", "mindset", "extra_args"]
        widgets = {"mindset": forms.Textarea(attrs={"rows": 5})}
