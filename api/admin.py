from django.contrib import admin
from .models import (
    UserProfile,
    StudentProfile,
    InstructorProfile,
    Course,
    Enrollment,
    Assignment,
    Materials,
    Submission,
    Notification,
    Scores,
)

admin.site.register(UserProfile)
admin.site.register(StudentProfile)
admin.site.register(InstructorProfile)
admin.site.register(Course)
admin.site.register(Enrollment)
admin.site.register(Assignment)
admin.site.register(Materials)
admin.site.register(Submission)
admin.site.register(Notification)
admin.site.register(Scores)