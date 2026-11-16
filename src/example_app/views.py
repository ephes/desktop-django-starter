from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import F
from django.http import HttpResponseRedirect, JsonResponse
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from .forms import ItemForm
from .models import Item
from .revisions import CONFLICT_MESSAGE, displayed_revision, matches_displayed_revision

PAGE_SIZE = 20


class ItemReturnNavigation:
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        page = self.request.GET.get("page", "")
        context["return_page"] = page if page.isascii() and page.isdigit() else ""
        return context

    def get_success_url(self):
        page = self.request.GET.get("page")
        if page:
            page = Paginator(Item.objects.all(), PAGE_SIZE).get_page(page).number
            return f"{self.success_url}?page={page}"
        return str(self.success_url)


class ItemListView(ListView):
    model = Item
    context_object_name = "items"
    paginate_by = PAGE_SIZE
    ordering = ["-updated_at", "-created_at", "-pk"]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        for item in context["items"]:
            item.displayed_revision = displayed_revision(item)
        return context


class ItemCreateView(ItemReturnNavigation, CreateView):
    form_class = ItemForm
    model = Item
    success_url = reverse_lazy("example_app:item-list")


class ItemUpdateView(ItemReturnNavigation, UpdateView):
    form_class = ItemForm
    model = Item
    success_url = reverse_lazy("example_app:item-list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["item_revision"] = (
            self.request.POST.get("revision", "")
            if self.request.method == "POST"
            else displayed_revision(self.object)
        )
        return context

    def post(self, request, *args, **kwargs):
        with transaction.atomic():
            # Own SQLite's writer before reading, also in local DEFERRED mode.
            Item.objects.filter(pk=kwargs["pk"]).update(title=F("title"))
            self.object = self.get_object()
            conflict = not matches_displayed_revision(self.object, request.POST.get("revision", ""))
            form = self.get_form()
            valid = form.is_valid()
            if conflict:
                form.add_error(None, CONFLICT_MESSAGE)
                return self.render_to_response(
                    self.get_context_data(form=form, revision_conflict=True), status=409
                )
            return self.form_valid(form) if valid else self.form_invalid(form)


class ItemDeleteView(ItemReturnNavigation, DeleteView):
    model = Item
    success_url = reverse_lazy("example_app:item-list")

    def form_valid(self, form):
        self.object.delete()
        return HttpResponseRedirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["item_revision"] = (
            self.request.POST.get("revision", "")
            if self.request.method == "POST"
            else displayed_revision(self.object)
        )
        return context

    def post(self, request, *args, **kwargs):
        with transaction.atomic():
            Item.objects.filter(pk=kwargs["pk"]).update(title=F("title"))
            self.object = self.get_object()
            if not matches_displayed_revision(self.object, request.POST.get("revision", "")):
                return self.render_to_response(
                    self.get_context_data(revision_conflict=CONFLICT_MESSAGE), status=409
                )
            return super().post(request, *args, **kwargs)


@require_POST
def item_clear(request):
    Item.objects.all().delete()
    return JsonResponse({"cleared": True})
