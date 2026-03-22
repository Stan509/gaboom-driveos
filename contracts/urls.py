from django.urls import path

from .views import contract_pdf_view, contract_sign_view

app_name = "contracts"

urlpatterns = [
    path("<int:pk>/pdf/", contract_pdf_view, name="contract_pdf"),
    path("<int:pk>/sign/", contract_sign_view, name="contract_sign"),
]
