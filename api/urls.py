from django.urls import path
from .views import *

urlpatterns = [

    path('login/', login_page, name='login_page'),
    path('student/dashboard/', student_dashboard, name='student_dashboard'),
    path('instructor/dashboard/', instructor_dashboard, name='instructor_dashboard'),
    path('logout/', logout_view, name='logout_view'),

    #user endpoints
    path('users/me/', user_profile, name='user_profile'),
    path('users/me/password/', user_password, name='user_password'),


    #course endpoints
    path('courses/', get_all_courses, name='get_courses'),
    path('courses/<int:course_id>/details/', get_course_details, name='course_details'),
    path('courses/instructor/', get_instructor_course, name='instructor_course'),
    path('courses/student/', get_student_courses, name='student_courses'),
    path('courses/<int:course_id>/create/', create_course_material, name='create_course'),


    #enrollment endpoints
    path('course/enrollments/', get_enrollments, name='course_enrollments'),
    path('courses/<int:course_id>/enroll/', course_enrollment, name='enroll_course'),
    path('courses/enrollments/<int:enrollment_id>/accept', accept_enrollment, name='accept_enrollment'),
    path('courses/enrollments/<int:enrollment_id>/reject', reject_enrollment, name='reject_enrollment'),

    #material endpoints
    path('materials/<int:material_id>/', view_course_material, name='view_course_material'),
    path('materials/<int:material_id>/modify/', modify_course_material, name='modify_course_material'),


    #assignment endpoints
    path('courses/<int:course_id>/assignments/instructor/', get_instructor_assignments, name='instructor_assignments'),
    path('courses/<int:course_id>/assignments/instructor/create', create_assignment, name='create_assignment'),
    path('courses/assignments/<int:assignment_id>/', get_assignment_details, name='assignment_details'),
    path('courses/assignments/<int:assignment_id>/modify/', modify_assignment, name='modify_assignment'),

    path('courses/assignments/student/', get_student_assignments, name='student_assignments'),
    path('courses/assignments/<int:assignment_id>/submit/', submit_assignment, name='submit_assignment'),
    

    #submission endpoints
    path('courses/assignments/<int:assignment_id>/submissions/', get_submissions, name='assignment_submissions'),
    path('courses/assignments/<int:assignment_id>/submissions/<int:submission_id>/', get_submission_details, name='submission_details'),

    #grade endpoints
    path('courses/grades/student/', get_student_grades, name='student_grades'),
    path('courses/assignments/<int:assignment_id>/submissions/<int:submission_id>/grade', grade_submission, name='grade_submission'),


]
