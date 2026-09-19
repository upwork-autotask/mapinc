from django.db import models


class AppSettings(models.Model):
    """Single-row table edited in admin. Always access it via AppSettings.load()."""

    DEFAULT_FILENAME_PATTERN = "CLINICALS REQUEST-{member_name}-SENT{MMDDYY}.pdf"

    attn_default = models.CharField("ATTN default", max_length=200, default="UR DEPARTMENT")
    client_default = models.CharField("Client default", max_length=200, default="WORLDTRIPS")
    doctor_default = models.CharField("Doctor default", max_length=200, default="RICHARD ABDALLAH",
                                      help_text='Printed after "Dr." in the letter.')
    pdf_root_folder = models.CharField(
        "PDF root folder", max_length=500, blank=True,
        help_text=r"Local or UNC path, e.g. \server\claims. Access passes the sub-folder name.")
    pdf_filename_pattern = models.CharField(
        "PDF filename pattern", max_length=200, default=DEFAULT_FILENAME_PATTERN,
        help_text="Placeholders: {member_name} {policy_id} {case_encounter} {MMDDYY} {YYYYMMDD}")
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
    # snapshot of the defaults used at generation time
    attn = models.CharField(max_length=200)
    client = models.CharField(max_length=200)
    doctor = models.CharField(max_length=200)
    folder_name = models.CharField(max_length=300)
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
