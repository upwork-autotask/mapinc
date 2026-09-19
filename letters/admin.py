from django.contrib import admin, messages
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.html import format_html

from . import audit
from .docgen.service import LetterGenerationError, generate_letter
from .forms import AppSettingsForm
from .models import AppSettings, AuditEvent, Letter

admin.site.site_header = "MAP Inc – Clinicals Request"
admin.site.site_title = "MAP Inc"
admin.site.index_title = "Administration"


@admin.register(AppSettings)
class AppSettingsAdmin(admin.ModelAdmin):
    form = AppSettingsForm
    fieldsets = (
        ("Letter defaults", {"fields": ("attn_default", "client_default", "doctor_default")}),
        ("PDF output", {"fields": ("pdf_root_folder", "pdf_filename_pattern")}),
        ("Word template", {"fields": ("template",)}),
    )

    def has_add_permission(self, request):
        return not AppSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        return redirect(reverse("admin:letters_appsettings_change", args=[AppSettings.load().pk]))


@admin.register(Letter)
class LetterAdmin(admin.ModelAdmin):
    list_display = ("case_encounter", "policy_id", "member_name", "created_by", "created_at",
                    "modified_by", "modified_at", "pdf_link")
    search_fields = ("case_encounter", "policy_id", "member_name")
    list_filter = ("created_at", "modified_at")
    readonly_fields = [f.name for f in Letter._meta.fields if f.name != "id"] + ["pdf_link"]
    actions = ["regenerate_pdf"]

    def has_add_permission(self, request):
        return False

    @admin.display(description="PDF")
    def pdf_link(self, obj):
        if not obj.pdf_path:
            return "—"
        return format_html('<a href="{}" target="_blank" rel="noopener">Open PDF</a>',
                           reverse("letter_pdf", args=[obj.case_encounter]))

    @admin.action(description="Regenerate PDF with stored values")
    def regenerate_pdf(self, request, queryset):
        for letter in queryset:
            data = {name: getattr(letter, name) for name in
                    ("case_encounter", "policy_id", "member_name", "dob", "admission", "folder_name")}
            try:
                generate_letter(data, request.user.get_username())
            except LetterGenerationError as exc:
                audit.record(request, AuditEvent.Action.LETTER_FAILED,
                             case_encounter=letter.case_encounter, detail=str(exc))
                self.message_user(request, f"{letter.case_encounter}: {exc}", messages.ERROR)
            else:
                audit.record(request, AuditEvent.Action.PDF_REGENERATED, case_encounter=letter.case_encounter)
                self.message_user(request, f"{letter.case_encounter}: PDF regenerated.", messages.SUCCESS)


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ("at", "user", "windows_user", "ip", "action", "case_encounter", "detail")
    list_filter = ("action", "at")
    search_fields = ("user", "windows_user", "case_encounter", "detail")
    readonly_fields = [f.name for f in AuditEvent._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
