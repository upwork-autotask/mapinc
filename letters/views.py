from pathlib import Path

from django.core.exceptions import ValidationError
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods

from .docgen.service import LetterGenerationError, generate_letter
from .forms import LetterForm
from .models import AppSettings, Letter

QUERY_FIELDS = ("case_encounter", "policy_id", "member_name", "dob", "admission", "folder_name", "user")
LETTER_FIELDS = ("case_encounter", "policy_id", "member_name", "dob", "admission", "folder_name")


def _parse_dob(value: str):
    try:
        return LetterForm.base_fields["dob"].to_python(value)
    except ValidationError:
        return value  # let the form report it on submit


def _initial_from_request(request) -> dict:
    """Existing letter (by case_encounter) first, then query-string values override field by field."""
    initial: dict = {}
    case_encounter = request.GET.get("case_encounter", "").strip()
    if case_encounter:
        existing = Letter.objects.filter(case_encounter=case_encounter).first()
        if existing:
            initial.update({name: getattr(existing, name) for name in LETTER_FIELDS})
    for name in QUERY_FIELDS:
        value = (request.GET.get(name) or "").strip()
        if value:
            initial[name] = _parse_dob(value) if name == "dob" else value
    return initial


@require_http_methods(["GET", "POST"])
def letter_form(request):
    context = {"app_settings": AppSettings.load()}
    if request.method == "POST":
        form = LetterForm(request.POST)
        if form.is_valid():
            try:
                letter = generate_letter(form.cleaned_data, form.cleaned_data.get("user", ""))
            except LetterGenerationError as exc:
                form.add_error(None, str(exc))
            else:
                return render(request, "letters/success.html", {**context, "letter": letter})
    else:
        form = LetterForm(initial=_initial_from_request(request))
    return render(request, "letters/form.html", {**context, "form": form})


def letter_pdf(request, case_encounter: str):
    letter = get_object_or_404(Letter, case_encounter=case_encounter)
    path = Path(letter.pdf_path) if letter.pdf_path else None
    if path is None or not path.is_file():
        raise Http404("PDF not found")
    return FileResponse(open(path, "rb"), content_type="application/pdf", filename=path.name)
