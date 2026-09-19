import csv
import datetime as dt
import json
from pathlib import Path

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import FileResponse, Http404, HttpResponse, HttpResponseBadRequest, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from . import audit
from .decorators import staff_required
from .docgen.service import LetterGenerationError, generate_letter
from .forms import AppSettingsForm, LetterForm
from .models import AppSettings, AuditEvent, Handoff, Letter

Action = AuditEvent.Action

QUERY_FIELDS = ("case_encounter", "policy_id", "member_name", "dob", "admission", "folder_name", "user")
LETTER_FIELDS = ("case_encounter", "policy_id", "member_name", "dob", "admission", "folder_name")


def _parse_dob(value: str):
    try:
        return LetterForm.base_fields["dob"].to_python(value)
    except ValidationError:
        return value  # let the form report it on submit


def _initial_from_request(request) -> tuple[dict, bool]:
    """
    Prefill order: existing letter (by case_encounter), then values stashed by a
    handoff token (?t=), then explicit query-string values, each overriding the
    last field by field. Returns (initial, token_expired).
    """
    params: dict = {}
    expired = False
    token = request.GET.get("t", "").strip()
    if token:
        stashed = Handoff.take(token)
        expired = stashed is None
        params.update(stashed or {})
    params.update({name: request.GET[name] for name in QUERY_FIELDS if name in request.GET})

    initial: dict = {}
    case_encounter = (params.get("case_encounter") or "").strip()
    if case_encounter:
        existing = Letter.objects.filter(case_encounter=case_encounter).first()
        if existing:
            initial.update({name: getattr(existing, name) for name in LETTER_FIELDS})
    for name in QUERY_FIELDS:
        value = (params.get(name) or "").strip()
        if value:
            initial[name] = _parse_dob(value) if name == "dob" else value
    return initial, expired


@require_http_methods(["GET", "POST"])
def letter_form(request):
    context = {"app_settings": AppSettings.load()}
    if request.method == "POST":
        form = LetterForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            windows_user = data.get("user", "")
            existed = Letter.objects.filter(case_encounter=data["case_encounter"]).exists()
            try:
                letter = generate_letter(data, windows_user)
            except LetterGenerationError as exc:
                audit.record(request, Action.LETTER_FAILED, case_encounter=data["case_encounter"],
                             detail=str(exc), windows_user=windows_user)
                form.add_error(None, str(exc))
            else:
                audit.record(request, Action.LETTER_UPDATED if existed else Action.LETTER_CREATED,
                             case_encounter=letter.case_encounter, detail=Path(letter.pdf_path).name,
                             windows_user=windows_user)
                return render(request, "letters/success.html", {**context, "letter": letter})
    else:
        initial, expired = _initial_from_request(request)
        form = LetterForm(initial=initial)
        context["token_expired"] = expired
        if initial.get("case_encounter"):
            audit.record(request, Action.FORM_OPENED, case_encounter=initial["case_encounter"],
                         detail="token" if request.GET.get("t") else "query",
                         windows_user=initial.get("user", ""))
    return render(request, "letters/form.html", {**context, "form": form})


def letter_pdf(request, case_encounter: str):
    letter = get_object_or_404(Letter, case_encounter=case_encounter)
    path = Path(letter.pdf_path) if letter.pdf_path else None
    if path is None or not path.is_file():
        raise Http404("PDF not found")
    audit.record(request, Action.PDF_DOWNLOADED, case_encounter=letter.case_encounter, detail=path.name)
    return FileResponse(open(path, "rb"), content_type="application/pdf", filename=path.name)


SETTINGS_GROUPS = (
    ("Letter defaults", ("attn_default", "client_default", "doctor_default")),
    ("PDF output", ("pdf_root_folder", "pdf_filename_pattern")),
    ("Word template", ("template",)),
)


@staff_required
@require_http_methods(["GET", "POST"])
def settings_page(request):
    app_settings = AppSettings.load()
    if request.method == "POST":
        form = AppSettingsForm(request.POST, request.FILES, instance=app_settings)
        if form.is_valid():
            form.save()
            audit.record(request, Action.SETTINGS_CHANGED, detail=", ".join(form.changed_data) or "no changes")
            messages.success(request, "Settings saved.")
            return redirect("settings")
    else:
        form = AppSettingsForm(instance=app_settings)
    groups = [(title, [form[name] for name in names]) for title, names in SETTINGS_GROUPS]
    return render(request, "letters/settings.html",
                  {"form": form, "groups": groups, "app_settings": app_settings})


def admin_login_redirect(request):
    """Send the Django admin's login to the branded /login/ page, keeping ?next=."""
    return redirect(f"{reverse('login')}?next={request.GET.get('next', reverse('admin:index'))}")


LIST_PAGE_SIZE = 25


@staff_required
def letter_list(request):
    """History of generated letters, newest change first, with a simple search box."""
    q = request.GET.get("q", "").strip()
    letters = Letter.objects.all()
    if q:
        letters = letters.filter(
            Q(case_encounter__icontains=q) | Q(policy_id__icontains=q) | Q(member_name__icontains=q))
    page = Paginator(letters, LIST_PAGE_SIZE).get_page(request.GET.get("page"))
    audit.record(request, Action.LIST_VIEWED, detail=f"q={q} page={page.number}")
    return render(request, "letters/list.html", {"page": page, "q": q, "total": page.paginator.count})


@csrf_exempt
@require_http_methods(["POST"])
def letter_handoff(request):
    """
    Called by the Access/Outlook launcher: stash the field values and answer
    with the URL to open (plain text), so the browser URL carries only a token.
    Accepts form-encoded or JSON bodies with the query-string field names.
    """
    if request.content_type == "application/json":
        try:
            payload = json.loads(request.body or b"{}")
        except ValueError:
            return HttpResponseBadRequest("invalid JSON")
    else:
        payload = request.POST
    data = {name: str(payload.get(name) or "").strip() for name in QUERY_FIELDS}
    token = Handoff.create(data)
    url = request.build_absolute_uri(f"{reverse('letter_form')}?t={token}")
    return HttpResponse(url, content_type="text/plain; charset=utf-8")


AUDIT_PAGE_SIZE = 50
AUDIT_CSV_COLUMNS = ("at", "user", "windows_user", "ip", "action", "case_encounter", "detail")


def _parse_date(value: str) -> dt.date | None:
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        return None


@staff_required
def audit_log(request):
    """Read-only audit trail with date/user/action/case filters and CSV export."""
    filters = {name: request.GET.get(name, "").strip() for name in ("from", "to", "user", "action", "q")}
    events = AuditEvent.objects.all()
    if date_from := _parse_date(filters["from"]):
        events = events.filter(at__date__gte=date_from)
    if date_to := _parse_date(filters["to"]):
        events = events.filter(at__date__lte=date_to)
    if filters["user"]:
        events = events.filter(Q(user__icontains=filters["user"]) | Q(windows_user__icontains=filters["user"]))
    if filters["action"]:
        events = events.filter(action=filters["action"])
    if filters["q"]:
        events = events.filter(Q(case_encounter__icontains=filters["q"]) | Q(detail__icontains=filters["q"]))

    if request.GET.get("format") == "csv":
        return _audit_csv(events)

    page = Paginator(events, AUDIT_PAGE_SIZE).get_page(request.GET.get("page"))
    query = request.GET.copy()
    query.pop("page", None)
    return render(request, "letters/audit.html", {
        "page": page, "filters": filters, "actions": AuditEvent.Action.choices,
        "total": page.paginator.count, "querystring": query.urlencode(),
    })


class _Echo:
    """csv.writer target that hands each line straight back."""

    @staticmethod
    def write(value):
        return value


def _audit_csv(events):
    writer = csv.writer(_Echo())

    def rows():
        yield writer.writerow(AUDIT_CSV_COLUMNS)
        for e in events.iterator(chunk_size=500):
            yield writer.writerow([timezone.localtime(e.at).isoformat(timespec="seconds"), e.user, e.windows_user,
                                   e.ip or "", e.action, e.case_encounter, e.detail])

    stamp = timezone.localdate().isoformat()
    response = StreamingHttpResponse(rows(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="mapinc-audit-{stamp}.csv"'
    return response
