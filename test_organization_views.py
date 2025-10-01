#!/usr/bin/env python3
"""
Test script for organization search functionality
Run this script to verify that the organization search views work correctly
"""

import os
import sys
import django

# Add the project directory to Python path
sys.path.insert(0, '/home/trucddx/OJ')

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dmoj.settings')
django.setup()

from django.test import RequestFactory
from django.contrib.auth.models import AnonymousUser
from django.contrib.auth import get_user_model
from judge.views.organization import OrganizationList, OrganizationSearchView, MyOrganizationsView
from judge.models import Organization, Profile

User = get_user_model()

def test_organization_views():
    """Test the organization views"""
    factory = RequestFactory()
    
    print("🧪 Testing Organization Views")
    print("=" * 50)
    
    # Test OrganizationList view
    print("\n1. Testing OrganizationList view...")
    request = factory.get('/organizations/')
    request.user = AnonymousUser()
    
    try:
        view = OrganizationList.as_view()
        response = view(request)
        print(f"   ✅ OrganizationList view works (status: {response.status_code})")
    except Exception as e:
        print(f"   ❌ OrganizationList view error: {e}")
    
    # Test OrganizationList with search
    print("\n2. Testing OrganizationList with search...")
    request = factory.get('/organizations/?q=vnoi&type=open')
    request.user = AnonymousUser()
    
    try:
        view = OrganizationList.as_view()
        response = view(request)
        print(f"   ✅ OrganizationList search works (status: {response.status_code})")
    except Exception as e:
        print(f"   ❌ OrganizationList search error: {e}")
    
    # Test OrganizationSearchView
    print("\n3. Testing OrganizationSearchView...")
    request = factory.get('/organizations/search?q=university')
    request.user = AnonymousUser()
    
    try:
        view = OrganizationSearchView.as_view()
        response = view(request)
        print(f"   ✅ OrganizationSearchView works (status: {response.status_code})")
    except Exception as e:
        print(f"   ❌ OrganizationSearchView error: {e}")
    
    # Test MyOrganizationsView (requires authenticated user)
    print("\n4. Testing MyOrganizationsView...")
    request = factory.get('/organizations/my')
    
    # Try to get a test user
    try:
        user = User.objects.first()
        if user:
            request.user = user
            request.profile = Profile.objects.get(user=user)
            
            view = MyOrganizationsView.as_view()
            response = view(request)
            print(f"   ✅ MyOrganizationsView works (status: {response.status_code})")
        else:
            print("   ⚠️  No test users found - create some test data first")
    except Exception as e:
        print(f"   ❌ MyOrganizationsView error: {e}")
    
    # Test organization queryset functionality
    print("\n5. Testing organization querysets...")
    try:
        # Test basic queryset
        orgs = Organization.objects.filter(is_unlisted=False)
        print(f"   ✅ Found {orgs.count()} public organizations")
        
        # Test search queryset
        from django.db.models import Q, Count
        search_orgs = Organization.objects.filter(
            Q(name__icontains='university') | Q(slug__icontains='university')
        ).annotate(actual_member_count=Count('members'))
        print(f"   ✅ Found {search_orgs.count()} organizations matching 'university'")
        
    except Exception as e:
        print(f"   ❌ Queryset error: {e}")
    
    print("\n" + "=" * 50)
    print("🎉 Organization view testing completed!")
    print("\nNext steps:")
    print("1. Load test data: ./load_test_data.sh")
    print("2. Run development server: python manage.py runserver")
    print("3. Visit: http://localhost:8000/organizations/")

if __name__ == '__main__':
    test_organization_views()
