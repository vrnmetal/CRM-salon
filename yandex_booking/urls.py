"""
Маршруты Maps Booking Partner API под /yandex/v1/.

Базовый адрес, который указывается Яндексу при подключении:
    https://<ваш-домен>/yandex/v1
"""
from django.urls import path

from yandex_booking import api

urlpatterns = [
    path("yandex/v1/companies/feed", api.companies_feed, name="yx_companies_feed"),
    path("yandex/v1/companies/<str:company_id>/services", api.company_services, name="yx_services"),
    path("yandex/v1/companies/<str:company_id>/resources", api.company_resources, name="yx_resources"),
    path("yandex/v1/companies/<str:company_id>/resources/<str:resource_id>/reviews",
         api.resource_reviews, name="yx_reviews"),
    path("yandex/v1/companies/<str:company_id>/available_dates",
         api.available_dates, name="yx_available_dates"),
    path("yandex/v1/companies/<str:company_id>/available_time_slots",
         api.available_time_slots, name="yx_available_slots"),
    path("yandex/v1/companies/<str:company_id>/special_conditions",
         api.special_conditions, name="yx_special_conditions"),
    path("yandex/v1/bookings", api.bookings_create, name="yx_booking_create"),
    path("yandex/v1/bookings/<str:booking_id>", api.booking_detail, name="yx_booking_detail"),
    path("yandex/v1/prebookings", api.prebookings_create, name="yx_prebooking_create"),
    path("yandex/v1/prebookings/<str:prebooking_id>", api.prebooking_delete, name="yx_prebooking_delete"),
]
