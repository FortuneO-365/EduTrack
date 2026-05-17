from django.contrib import admin

from .models import (
    StudentProfile,
    InstructorProfile,
    Course,
    Enrollment,
    Assignment,
    Materials,
    Submission,
    Scores
)

# Register your models here.

admin.site.register(StudentProfile)
admin.site.register(InstructorProfile)
admin.site.register(Course)
admin.site.register(Enrollment)
admin.site.register(Assignment)
admin.site.register(Materials)
admin.site.register(Submission)
admin.site.register(Scores)