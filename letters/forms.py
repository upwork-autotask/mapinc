from django import forms

DATE_INPUT_FORMATS = ["%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"]


class LetterForm(forms.Form):
    case_encounter = forms.CharField(label="Case/Encounter", max_length=100)
    policy_id = forms.CharField(label="Policy ID No.", max_length=100)
    member_name = forms.CharField(label="Member Name", max_length=200)
    dob = forms.DateField(label="Date of Birth", input_formats=DATE_INPUT_FORMATS,
                          widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}))
    admission = forms.CharField(label="Admission", max_length=200)
    folder_name = forms.CharField(label="Folder", max_length=300)
    user = forms.CharField(required=False, widget=forms.HiddenInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("autocomplete", "off")
