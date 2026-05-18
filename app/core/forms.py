import copy
from django import forms
from .models import Project, ProjectMemory, ProjectPiSettings, UserPiSettings
from .utils import get_provider_choices, get_model_choices

# Static fallback choices (used if models.json unavailable)
STATIC_PROVIDER_CHOICES = [
    ("", "— select provider —"),
    ("anthropic", "Anthropic"),
    ("openai", "OpenAI"),
    ("openai-codex", "OpenAI Codex"),
    ("gemini", "Gemini"),
    ("bedrock", "AWS Bedrock"),
    ("vertex", "Google Vertex"),
    ("ollama", "Ollama (local)"),
]

STATIC_MODEL_CHOICES = [
    ("", "— select model —"),
    # Anthropic
    ("claude-opus-4-7", "Claude Opus 4.7"),
    ("claude-sonnet-4-6", "Claude Sonnet 4.6"),
    ("claude-haiku-4-5-20251022", "Claude Haiku 4.5"),
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


class DynamicChoiceField(forms.ChoiceField):
    """ChoiceField that reloads choices at widget rendering time."""
    def __init__(self, *args, choices_func=None, **kwargs):
        self.choices_func = choices_func
        # Set choices immediately so widget has them
        choices = choices_func() if choices_func else []
        super().__init__(*args, choices=choices, **kwargs)
    
    def __deepcopy__(self, memo):
        # Handle deepcopy properly - copy all needed attributes
        result = self.__class__.__new__(self.__class__)
        result.choices_func = self.choices_func
        result._choices = copy.deepcopy(self._choices, memo) if hasattr(self, '_choices') else []
        result.widget = copy.deepcopy(self.widget, memo)
        result.required = copy.deepcopy(self.required, memo)
        result.label = getattr(self, 'label', None)
        result.initial = getattr(self, 'initial', None)
        result.help_text = getattr(self, 'help_text', '')
        result.error_messages = copy.deepcopy(self.error_messages, memo)
        result.show_hidden_initial = getattr(self, 'show_hidden_initial', False)
        result.validators = copy.deepcopy(self.validators, memo)
        result.label_suffix = getattr(self, 'label_suffix', None)
        result.disabled = getattr(self, 'disabled', False)
        result.localize = getattr(self, 'localize', False)
        return result
    
    def valid_value(self, value):
        # Validate against current choices
        if self.choices_func:
            current_choices = self.choices_func()
            return value in [c[0] for c in current_choices]
        return super().valid_value(value)

THINKING_CHOICES = [
    ("", "— select thinking level —"),
    ("none", "None"),
    ("minimal", "Minimal"),
    ("low", "Low"),
    ("medium", "Medium"),
    ("high", "High"),
    ("auto", "Auto"),
]

PROJECT_PROVIDER_CHOICES = [("", "— use general setting —")]
PROJECT_MODEL_CHOICES = [("", "— use general setting —")]
PROJECT_THINKING_CHOICES = [
    ("", "— use general setting —"),
    ("none", "None"),
    ("minimal", "Minimal"),
    ("low", "Low"),
    ("medium", "Medium"),
    ("high", "High"),
    ("auto", "Auto"),
]


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
    provider = DynamicChoiceField(choices_func=get_provider_choices, required=False, widget=forms.Select(attrs={'class': 'form-select'}))
    model = DynamicChoiceField(choices_func=get_model_choices, required=False, widget=forms.Select(attrs={'class': 'form-select'}))
    thinking_level = forms.ChoiceField(choices=PROJECT_THINKING_CHOICES, required=False, widget=forms.Select(attrs={'class': 'form-select'}))

    class Meta:
        model = ProjectPiSettings
        fields = ["provider", "model", "thinking_level", "use_context_files", "extra_args"]
        widgets = {"use_context_files": forms.CheckboxInput()}
        labels = {"use_context_files": "Load AGENTS.md / CLAUDE.md context files"}


class UserPiSettingsForm(forms.ModelForm):
    provider = DynamicChoiceField(choices_func=get_provider_choices, required=False, widget=forms.Select(attrs={'class': 'form-select'}))
    model = DynamicChoiceField(choices_func=get_model_choices, required=False, widget=forms.Select(attrs={'class': 'form-select'}))
    thinking_level = forms.ChoiceField(choices=THINKING_CHOICES, required=False, widget=forms.Select(attrs={'class': 'form-select'}))

    class Meta:
        model = UserPiSettings
        fields = ["provider", "model", "thinking_level", "use_context_files", "extra_args"]
        widgets = {"use_context_files": forms.CheckboxInput()}
        labels = {"use_context_files": "Load AGENTS.md / CLAUDE.md context files"}
