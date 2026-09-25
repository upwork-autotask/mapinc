from django import forms
from django.db.models.fields.files import FieldFile

from .docgen.filenames import ALLOWED_PLACEHOLDERS, unknown_placeholders
from .docgen.template_fill import missing_bindings
from .models import AppSettings

DATE_INPUT_FORMATS = ["%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"]


class LetterForm(forms.Form):
    case_encounter = forms.CharField(label="Case/Encounter", max_length=100)
    policy_id = forms.CharField(label="Policy ID No.", max_length=100)
    member_name = forms.CharField(label="Member Name", max_length=200)
    dob = forms.DateField(label="Date of Birth", input_formats=DATE_INPUT_FORMATS,
                          widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}))
    admission = forms.CharField(label="Admission", max_length=200)
    # Supplied by the launcher for the PDF file name; not printed on the letter.
    case_location = forms.CharField(label="Case Location", max_length=100, required=False)
    case_type = forms.CharField(label="Case Type", max_length=100, required=False)
    # Filled by the Access/Outlook launcher with the whole destination path.
    folder_name = forms.CharField(label="Folder", max_length=500)
    user = forms.CharField(required=False, widget=forms.HiddenInput)
    token = forms.CharField(required=False, widget=forms.HiddenInput)  # handoff token, consumed on save

    def __init__(self, *args, editable=None, **kwargs):
        """`editable` is the set of field names the user may change; None means all of them."""
        super().__init__(*args, **kwargs)
        self.editable = set(self.fields) if editable is None else set(editable)
        for name, field in self.fields.items():
            field.widget.attrs.setdefault("autocomplete", "off")
            if name not in self.editable and not isinstance(field.widget, forms.HiddenInput):
                field.widget.attrs["readonly"] = "readonly"
                field.widget.attrs["tabindex"] = "-1"

    def locked(self, name: str) -> bool:
        return name not in self.editable


class AppSettingsForm(forms.ModelForm):
    """Used by both the custom /settings/ page and the Django admin."""

    class Meta:
        model = AppSettings
        fields = ["attn_default", "client_default", "doctor_default",
                  "pdf_filename_pattern", "template"]
        widgets = {"template": forms.FileInput(attrs={"accept": ".docx"})}

    def clean_pdf_filename_pattern(self):
        pattern = (self.cleaned_data.get("pdf_filename_pattern") or "").strip()
        unknown = unknown_placeholders(pattern)
        if unknown:
            raise forms.ValidationError(
                "This pattern uses %(unknown)s, which the app cannot fill. Use only: %(allowed)s",
                params={"unknown": ", ".join(unknown),
                        "allowed": ", ".join("{" + name + "}" for name in ALLOWED_PLACEHOLDERS)})
        return pattern

    def clean_template(self):
        upload = self.cleaned_data.get("template")
        if upload and not isinstance(upload, FieldFile):  # a new file, not the stored one
            data = upload.read()
            upload.seek(0)
            try:
                missing = missing_bindings(data)
            except Exception as exc:  # noqa: BLE001 - not a readable .docx
                raise forms.ValidationError(f"Not a valid Word .docx file ({exc}).") from exc
            if missing:
                raise forms.ValidationError(
                    "Template is missing content controls bound to: " + ", ".join(sorted(missing)))
        return upload
