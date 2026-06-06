from django.urls import path
from .views import *

urlpatterns = [

    path('login/', login_page, name='login_page'),
    path('student/dashboard/', student_dashboard, name='student_dashboard'),
    path('instructor/dashboard/', instructor_dashboard, name='instructor_dashboard'),
    path('logout/', logout_view, name='logout_view'),

    #user endpoints
    path('users/', get_users, name='get_users'),
    path('users/<int:pk>/', get_user_profile, name='get_user'),
    path('users/me/', user_profile, name='user_profile'),

    #auth endpoints
    path('auth/register/', register_user, name='register'),
    path('auth/login/', login_user, name='login-user'),

    #course endpoints
    path('courses/', get_all_courses, name='get_courses'),
    path('courses/<int:course_id>/details/', get_course_details, name='course_details'),
    path('courses/instructor/', get_instructor_course, name='instructor_course'),
    path('courses/student/', get_student_courses, name='student_courses'),
    path('courses/<int:course_id>/create/', create_course, name='create_course'),


    #enrollment endpoints
    path('course/enrollments/', get_enrollments, name='course_enrollments'),
    path('courses/<int:course_id>/enroll/', course_enrollment, name='enroll_course'),
    path('courses/enrollments/<int:enrollment_id>/accept', accept_enrollment, name='accept_enrollment'),
    path('courses/enrollments/<int:enrollment_id>/reject', reject_enrollment, name='reject_enrollment'),


    #assignment endpoints
    # path('courses/<int:course_id>/assignments/', get_assignments, name='get_assignments'),
    path('courses/<int:course_id>/assignments/instructor/', get_instructor_assignments, name='instructor_assignments'),
    path('courses/assignments/student/', get_student_assignments, name='student_assignments'),

    #grade endpoints
    path('courses/grades/student/', get_student_grades, name='student_grades'),
    # path('courses/<int:course_id>/grades/grades, name='get_grades'),


    # path('courses/<int:pk>/', modify_course, name='get_course'),
    # path('courses/create/', create_course, name='create_course'),



    #assignment endpoints

    #upload endpoints
]
