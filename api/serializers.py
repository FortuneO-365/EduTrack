from rest_framework import serializers
from .models import *

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name']

class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = ['user_type']

class StudentSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudentProfile
        fields = '__all__'

class InstructorSerializer(serializers.ModelSerializer):
    class Meta:
        model = InstructorProfile
        fields = '__all__'

class CourseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Course
        fields = '__all__'

class EnrollmentSerializer(serializers.ModelSerializer):
    student_first_name = serializers.CharField(source='student.user.first_name', read_only=True)
    student_last_name = serializers.CharField(source='student.user.last_name', read_only=True)
    student_full_name = serializers.CharField(source='student.user.get_full_name', read_only=True)

    class Meta:
        model = Enrollment
        fields = [
            'id',
            'student',
            'course',
            'status',
            'enrollment_date',
            'student_first_name',
            'student_last_name',
            'student_full_name',
        ]

class AssignmentSerializer(serializers.ModelSerializer):
    course_name = serializers.CharField(source='course.title', read_only=True)
    due_date = serializers.DateTimeField(
        format="%b %d, %Y - %I:%M %p"
    )
    class Meta:
        model = Assignment
        fields = [
            'id',
            'title',
            'description',
            'created_at',
            'due_date',
            'course',
            'course_name'
        ]

class MaterialsSerializer(serializers.ModelSerializer):
    class Meta:
        model = Materials
        fields = '__all__'

class SubmissionSerializer(serializers.ModelSerializer):
    student = serializers.CharField(source='student.user.username', read_only=True)
    submission_date = serializers.DateTimeField(
        format="%b %d, %Y - %I:%M %p"
    )
    class Meta:
        model = Submission
        fields = [
            'id',
            'assignment',
            'student',
            'file_name',
            'file_url',
            'submission_date',
            'status',
        ]

class ScoresSerializer(serializers.ModelSerializer):
    class Meta:
        model = Scores
        fields = '__all__'
