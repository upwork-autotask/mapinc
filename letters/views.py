import csv
import datetime as dt
import ipaddress
import json
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import (FileResponse, Http404, HttpResponse, HttpResponseBadRequest, HttpResponseForbidden,
                         JsonResponse, StreamingHttpResponse)
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from . import audit
from .decorators import letter_access, staff_required
from .docgen.filenames import InvalidFolderName, resolve_folder
from .docgen.service import LetterGenerationError, generate_letter
from .explorer import open_in_explorer
from .forms import AppSettingsForm, LetterForm
from .models import AppSettings, AuditEvent, Handoff, Letter

Action = AuditEvent.Action

QUERY_FIELDS = ("case_encounter", "policy_id", "member_name", "dob", "admission",
                "case_location", "case_type", "folder_name", "user")
LETTER_FIELDS = ("case_encounter", "policy_id", "member_name", "dob", "admission",
                 "case_location", "case_type", "folder_name")


def _is_admin(request) -> bool:
    return request.user.is_authenticated and request.user.is_staff


def _editable_fields(request, existing) -> set[str]:
    """
    New letter: everything except the folder, which the launcher supplies.
    Existing letter: only the admission — unless an administrator is signed in,
    who may correct every field (including the destination folder).
    """
    always = {"user", "token"}
    if _is_admin(request):
        return set(LETTER_FIELDS) | always
    if existing is None:
        return (set(LETTER_FIELDS) - {"folder_name"}) | always
    return {"admission"} | always


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
    # In production only the case number and user may come from the URL; PHI arrives via handoff tokens.
    allowed = QUERY_FIELDS if settings.MAPINC_ALLOW_QUERY_PREFILL else ("case_encounter", "user")
    params.update({name: request.GET[name] for name in allowed if name in request.GET})

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
    if token and not expired:
        initial["token"] = token
    return initial, expired


@letter_access
@require_http_methods(["GET", "POST"])
def letter_form(request):
    context = {"app_settings": AppSettings.load()}
    if request.method == "POST":
        existing = Letter.objects.filter(case_encounter=request.POST.get("case_encounter", "").strip()).first()
        editable = _editable_fields(request, existing)
        form = LetterForm(request.POST, editable=editable)
        if form.is_valid():
            data = dict(form.cleaned_data)
            if existing is not None:
                # A locked field keeps the value already on record, whatever was posted.
                for name in LETTER_FIELDS:
                    if name not in editable:
                        data[name] = getattr(existing, name)
            windows_user = data.get("user", "")
            # A verified identity (app login or Windows auth) beats the launcher's self-reported name.
            actor = request.user.get_username() if request.user.is_authenticated else windows_user
            existed = existing is not None
            try:
                letter = generate_letter(data, actor)
            except LetterGenerationError as exc:
                audit.record(request, Action.LETTER_FAILED, case_encounter=data["case_encounter"],
                             detail=str(exc), windows_user=windows_user)
                form.add_error(None, str(exc))
            else:
                Handoff.consume(data.get("token", ""))
                audit.record(request, Action.LETTER_UPDATED if existed else Action.LETTER_CREATED,
                             case_encounter=letter.case_encounter, detail=Path(letter.pdf_path).name,
                             windows_user=windows_user)
                return render(request, "letters/success.html", {**context, "letter": letter})
    else:
        initial, expired = _initial_from_request(request)
        existing = Letter.objects.filter(case_encounter=initial.get("case_encounter", "")).first()
        # A letter that already exists opens read-only; "Edit" (?edit=1) unlocks it.
        edit_mode = existing is None or request.GET.get("edit") == "1"
        editable = _editable_fields(request, existing) if edit_mode else set()
        form = LetterForm(initial=initial, editable=editable)
        context.update({
            "token_expired": expired,
            "existing": existing,
            "edit_mode": edit_mode,
            "is_admin": _is_admin(request),
            "pdf_exists": bool(existing and existing.pdf_path and Path(existing.pdf_path).is_file()),
            "pdf_name": Path(existing.pdf_path).name if existing and existing.pdf_path else "",
            # auto_now / auto_now_add differ by microseconds on a fresh row, so allow a second
            "was_edited": bool(existing and ((existing.modified_at - existing.created_at).total_seconds() > 1
                                             or existing.modified_by != existing.created_by)),
        })
        if initial.get("case_encounter"):
            audit.record(request, Action.FORM_OPENED, case_encounter=initial["case_encounter"],
                         detail="token" if request.GET.get("t") else "query",
                         windows_user=initial.get("user", ""))
    return render(request, "letters/form.html", {**context, "form": form})


@letter_access
def letter_pdf(request, case_encounter: str):
    letter = get_object_or_404(Letter, case_encounter=case_encounter)
    path = Path(letter.pdf_path) if letter.pdf_path else None
    if path is None or not path.is_file():
        raise Http404("PDF not found")
    audit.record(request, Action.PDF_DOWNLOADED, case_encounter=letter.case_encounter, detail=path.name)
    return FileResponse(open(path, "rb"), content_type="application/pdf", filename=path.name)


SETTINGS_GROUPS = (
    ("Letter defaults", ("attn_default", "client_default", "doctor_default")),
    ("PDF output", ("pdf_filename_pattern",)),
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
    if not _handoff_allowed(request):
        return HttpResponseForbidden("handoff not allowed from this address")
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


LOOPBACK = {"127.0.0.1", "::1"}


@letter_access
@require_http_methods(["POST"])
def open_folder(request):
    """
    Open the letter's folder in Explorer. Browsers refuse file:// links from a web
    page, so the page asks the server instead — which is only correct when the
    browser is on the server itself, hence the loopback check. Remote browsers get
    "remote" back and fall back to the URL-protocol handler or the clipboard.
    """
    if not settings.MAPINC_LOCAL_EXPLORER:
        return JsonResponse({"opened": False, "reason": "disabled"})
    if audit.client_ip(request) not in LOOPBACK:
        return JsonResponse({"opened": False, "reason": "remote"})

    letter = Letter.objects.filter(case_encounter=request.POST.get("case_encounter", "").strip()).first()
    try:
        folder = resolve_folder(letter.folder_name if letter else request.POST.get("path", ""))
    except InvalidFolderName as exc:
        return JsonResponse({"opened": False, "reason": str(exc)}, status=400)
    if not folder.is_dir():
        return JsonResponse({"opened": False, "reason": f"The folder does not exist yet: {folder}"}, status=404)

    return JsonResponse({"opened": open_in_explorer(folder), "path": str(folder)})


def _handoff_allowed(request) -> bool:
    """[app] handoff_allowed_networks: empty = anyone; otherwise the caller must be inside one of the CIDRs."""
    networks = settings.MAPINC_HANDOFF_ALLOWED_NETWORKS
    if not networks:
        return True
    try:
        ip = ipaddress.ip_address(audit.client_ip(request) or "")
    except ValueError:
        return False
    return any(ip in ipaddress.ip_network(n, strict=False) for n in networks)
