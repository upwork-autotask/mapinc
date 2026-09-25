import secrets
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


class AppSettings(models.Model):
    """Single-row table edited in admin. Always access it via AppSettings.load()."""

    DEFAULT_FILENAME_PATTERN = ("{case_encounter}-{case_location}-{case_type}-CLINICALS REQUEST-"
                                "{member_name}-SENT{MMDDYY}-{user}.pdf")

    attn_default = models.CharField("ATTN default", max_length=200, default="UR DEPARTMENT")
    client_default = models.CharField("Client default", max_length=200, default="WORLDTRIPS")
    doctor_default = models.CharField("Doctor default", max_length=200, default="RICHARD ABDALLAH",
                                      help_text='Printed after "Dr." in the letter.')
    pdf_filename_pattern = models.CharField(
        "PDF filename pattern", max_length=200, default=DEFAULT_FILENAME_PATTERN,
        help_text="Placeholders: {case_encounter} {policy_id} {member_name} {case_location} "
                  "{case_type} {user} {MMDDYY} {YYYYMMDD}. Values the launcher did not send are "
                  "left out and the extra separators removed.")
    template = models.FileField("Word template (.docx)", upload_to="templates/", blank=True)

    class Meta:
        verbose_name = "Settings"
        verbose_name_plural = "Settings"

    def __str__(self):
        return "Application settings"

    @classmethod
    def load(cls) -> "AppSettings":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def save(self, *args, **kwargs):
        self.pk = 1  # enforce the singleton
        super().save(*args, **kwargs)

    def template_bytes(self) -> bytes:
        if not self.template:
            raise ValueError("No Word template uploaded. Set it in admin > Settings.")
        with self.template.open("rb") as fh:
            return fh.read()


class Letter(models.Model):
    """One generated Clinicals Request letter per case/encounter."""

    case_encounter = models.CharField("Case/Encounter", max_length=100, unique=True)
    policy_id = models.CharField("Policy ID", max_length=100)
    member_name = models.CharField(max_length=200)
    dob = models.DateField("Date of birth")
    admission = models.CharField(max_length=200)
    # extra values the launcher supplies; used in the PDF file name, not printed on the letter
    case_location = models.CharField("Case location", max_length=100, blank=True)
    case_type = models.CharField("Case type", max_length=100, blank=True)
    # snapshot of the defaults used at generation time
    attn = models.CharField(max_length=200)
    client = models.CharField(max_length=200)
    doctor = models.CharField(max_length=200)
    folder_name = models.CharField("Folder", max_length=500,
                                   help_text="Full destination folder supplied by the launcher.")
    pdf_path = models.CharField(max_length=1000, blank=True)
    docx_path = models.CharField(max_length=1000, blank=True)
    created_by = models.CharField(max_length=150)
    created_at = models.DateTimeField(auto_now_add=True)
    modified_by = models.CharField(max_length=150)
    modified_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-modified_at"]

    def __str__(self):
        return f"{self.case_encounter} – {self.member_name}"


class Handoff(models.Model):
    """
    Short-lived stash of the values Access/Outlook wants pre-filled, so the
    letter URL carries only an opaque token instead of patient data.
    """

    token = models.CharField(max_length=64, unique=True)
    data = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.token

    @staticmethod
    def ttl() -> timedelta:
        return timedelta(minutes=getattr(settings, "MAPINC_HANDOFF_MINUTES", 5))

    @classmethod
    def purge_expired(cls) -> int:
        deleted, _ = cls.objects.filter(created_at__lt=timezone.now() - cls.ttl()).delete()
        return deleted

    @classmethod
    def create(cls, data: dict) -> str:
        cls.purge_expired()
        return cls.objects.create(token=secrets.token_urlsafe(24), data=dict(data)).token

    @classmethod
    def take(cls, token: str) -> dict | None:
        """The stashed values, or None if the token is unknown or older than the TTL."""
        row = cls.objects.filter(token=token, created_at__gte=timezone.now() - cls.ttl()).first()
        return dict(row.data) if row else None

    @classmethod
    def consume(cls, token: str) -> None:
        """Invalidate a token once the letter it carried has been saved."""
        if token:
            cls.objects.filter(token=token).delete()


class AuditEvent(models.Model):
    """
    Insert-only trail of who did what with patient data (HIPAA audit controls).
    `user` is the authenticated app/Windows account; `windows_user` is the name
    the Access/Outlook launcher supplied (self-reported unless auth_mode=remote_user).
    """

    class Action(models.TextChoices):
        FORM_OPENED = "form_opened", "Letter form opened"
        LETTER_CREATED = "letter_created", "Letter created"
        LETTER_UPDATED = "letter_updated", "Letter updated"
        LETTER_FAILED = "letter_failed", "Letter generation failed"
        PDF_DOWNLOADED = "pdf_downloaded", "PDF downloaded"
        PDF_REGENERATED = "pdf_regenerated", "PDF regenerated"
        LIST_VIEWED = "list_viewed", "Letters list viewed"
        SETTINGS_CHANGED = "settings_changed", "Settings changed"
        LOGIN = "login", "Login"
        LOGOUT = "logout", "Logout"
        LOGIN_FAILED = "login_failed", "Login failed"
        LOCKOUT = "lockout", "Account locked out"

    at = models.DateTimeField(auto_now_add=True, db_index=True)
    user = models.CharField(max_length=150, blank=True, db_index=True)
    windows_user = models.CharField(max_length=150, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    action = models.CharField(max_length=32, choices=Action.choices, db_index=True)
    case_encounter = models.CharField(max_length=100, blank=True, db_index=True)
    detail = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["-at", "-id"]

    def __str__(self):
        return f"{self.at:%Y-%m-%d %H:%M} {self.user or self.windows_user} {self.action} {self.case_encounter}"
