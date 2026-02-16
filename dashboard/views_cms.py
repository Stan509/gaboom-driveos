from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.text import slugify

from core.decorators import require_agency_admin, require_agency_user
from public_site.models import PublicPage


# ── helpers ──────────────────────────────────────────────────────────

def _agency(request):
    return request.user.agency


def _unique_slug(agency, title, exclude_pk=None):
    base = slugify(title) or "page"
    slug = base
    i = 1
    while PublicPage.objects.filter(agency=agency, slug=slug).exclude(pk=exclude_pk).exists():
        i += 1
        slug = f"{base}-{i}"
    return slug


def _redirect_next(request, fallback):
    next_url = request.POST.get("next") or request.GET.get("next")
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)
    return redirect(fallback)


# ── List ─────────────────────────────────────────────────────────────

@require_agency_user
def cms_page_list(request: HttpRequest) -> HttpResponse:
    base = reverse("dashboard:site_public_settings")
    query = request.GET.urlencode()
    url = f"{base}?{query}" if query else base
    return redirect(url)


# ── Create ───────────────────────────────────────────────────────────

@require_agency_admin
def cms_page_create(request: HttpRequest) -> HttpResponse:
    agency = _agency(request)

    if request.method == "POST":
        title = request.POST.get("title", "").strip()[:200]
        slug = request.POST.get("slug", "").strip()[:200]
        content = request.POST.get("content", "")
        is_published = request.POST.get("is_published") == "on"
        show_in_nav = request.POST.get("show_in_nav") == "on"
        nav_order = int(request.POST.get("nav_order", 0) or 0)
        template_variant = request.POST.get("template_variant", "default")
        cta_label = request.POST.get("cta_label", "").strip()[:100]
        cta_url = request.POST.get("cta_url", "").strip()[:500]
        seo_title = request.POST.get("seo_title", "").strip()[:200]
        seo_description = request.POST.get("seo_description", "").strip()

        if not title:
            messages.error(request, "Le titre est requis.")
            return redirect("dashboard:cms_page_create")

        if not slug:
            slug = _unique_slug(agency, title)
        else:
            slug = slugify(slug)
            if PublicPage.objects.filter(agency=agency, slug=slug).exists():
                slug = _unique_slug(agency, title)

        page = PublicPage.objects.create(
            agency=agency,
            title=title,
            slug=slug,
            content=content,
            is_published=is_published,
            show_in_nav=show_in_nav,
            nav_order=nav_order,
            template_variant=template_variant,
            cta_label=cta_label,
            cta_url=cta_url,
            seo_title=seo_title,
            seo_description=seo_description,
        )
        messages.success(request, f'Page "{page.title}" créée.')
        return _redirect_next(request, reverse("dashboard:site_public_settings") + "?panel=pages")

    return redirect(reverse("dashboard:site_public_settings") + "?panel=pages&cms_create=1")


# ── Edit ─────────────────────────────────────────────────────────────

@require_agency_admin
def cms_page_edit(request: HttpRequest, pk: int) -> HttpResponse:
    agency = _agency(request)
    page = get_object_or_404(PublicPage, pk=pk, agency=agency)

    if request.method == "POST":
        page.title = request.POST.get("title", page.title).strip()[:200]
        new_slug = request.POST.get("slug", "").strip()[:200]
        if new_slug:
            new_slug = slugify(new_slug)
            if new_slug != page.slug and PublicPage.objects.filter(agency=agency, slug=new_slug).exclude(pk=pk).exists():
                messages.error(request, "Ce slug est déjà utilisé.")
                return redirect("dashboard:cms_page_edit", pk=pk)
            page.slug = new_slug

        page.content = request.POST.get("content", page.content)
        page.is_published = request.POST.get("is_published") == "on"
        page.show_in_nav = request.POST.get("show_in_nav") == "on"
        page.nav_order = int(request.POST.get("nav_order", 0) or 0)
        page.template_variant = request.POST.get("template_variant", "default")
        page.cta_label = request.POST.get("cta_label", "").strip()[:100]
        page.cta_url = request.POST.get("cta_url", "").strip()[:500]
        page.seo_title = request.POST.get("seo_title", "").strip()[:200]
        page.seo_description = request.POST.get("seo_description", "").strip()
        page.save()
        messages.success(request, f'Page "{page.title}" mise à jour.')
        return _redirect_next(request, reverse("dashboard:site_public_settings") + "?panel=pages")

    return redirect(reverse("dashboard:site_public_settings") + f"?panel=pages&cms_edit={page.pk}")


# ── Delete ───────────────────────────────────────────────────────────

@require_agency_admin
def cms_page_delete(request: HttpRequest, pk: int) -> HttpResponse:
    agency = _agency(request)
    page = get_object_or_404(PublicPage, pk=pk, agency=agency)
    title = page.title
    page.delete()
    messages.success(request, f'Page "{title}" supprimée.')
    return _redirect_next(request, reverse("dashboard:site_public_settings") + "?panel=pages")
