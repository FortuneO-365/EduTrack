from django.urls import path
from .views import *

urlpatterns = [

    path('login/', login_page, name='login'),

    #user endpoints
    path('users/', get_user, name='get_user'),

    #auth endpoints
    path('auth/register/', register_user, name='register'),
    path('auth/login/', login_user, name='login'),

    #course endpoints
    path('courses/', get_courses, name='get_courses'),
    path('courses/<int:pk>/', modify_course, name='get_course'),
    path('courses/create/', create_course, name='create_course'),



    #assignment endpoints

    #upload endpoints
]