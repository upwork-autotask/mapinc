from django import forms
from django.contrib import admin, messages
from django.db.models.fields.files import FieldFile
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.html import format_html

from .docgen.service import LetterGenerationError, generate_letter
from .docgen.template_fill import missing_bindings
from .models import AppSettings, Letter

admin.site.site_header = "MAP Inc – Clinicals Request"
admin.site.site_title = "MAP Inc"
admin.site.index_title = "Administration"


class AppSettingsForm(forms.ModelForm):
    class Meta:
        model = AppSettings
        fields = "__all__"

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
                self.message_user(request, f"{letter.case_encounter}: {exc}", messages.ERROR)
            else:
                self.message_user(request, f"{letter.case_encounter}: PDF regenerated.", messages.SUCCESS)
