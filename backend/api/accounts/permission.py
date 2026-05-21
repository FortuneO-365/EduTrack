from rest_framework.permissions import BasePermission

class IsStudent(BasePermission):
    def has_permission(self, request, view):
        if request.user.is_authenticated and request.user.groups.filter(name='Student').exists():
            return True
        return False

class IsInstructor(BasePermission):
    def has_permission(self, request, view):
        if request.user.is_authenticated and request.user.groups.filter(name='Instructor').exists():
            return True
        return False
    
class IsInstructorOrStudent(BasePermission):
    def has_permission(self, request, view):
        if request.user.is_authenticated and (request.user.groups.filter(name='Instructor').exists() or request.user.groups.filter(name='Student').exists()):
            return True
        return False