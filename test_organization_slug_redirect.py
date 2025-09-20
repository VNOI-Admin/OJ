#!/usr/bin/env python3
"""
Test script for organization slug redirect functionality
"""

import os
import sys
import django
from django.conf import settings

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dmoj.settings')
django.setup()

from judge.models import Organization, OrganizationSlugHistory
from django.test import Client
from django.urls import reverse

def test_organization_slug_redirect():
    """Test the organization slug redirect functionality"""
    
    print("=== Testing Organization Slug Redirect Functionality ===\n")
    
    # Create a test organization
    print("1. Creating test organization...")
    try:
        # Delete existing test org if it exists
        try:
            old_org = Organization.objects.get(slug='test-org')
            old_org.delete()
            print("   Deleted existing test organization")
        except Organization.DoesNotExist:
            pass
            
        org = Organization.objects.create(
            name='Test Organization',
            slug='test-org',
            short_name='TestOrg',
            about='Test organization for slug redirect testing'
        )
        print(f"   Created organization: {org.name} with slug: {org.slug}")
    except Exception as e:
        print(f"   Error creating organization: {e}")
        return False
    
    # Change the slug to simulate a slug change
    print("\n2. Changing organization slug...")
    try:
        old_slug = org.slug
        new_slug = 'test-org-new'
        org.slug = new_slug
        org.save()
        print(f"   Changed slug from '{old_slug}' to '{new_slug}'")
    except Exception as e:
        print(f"   Error changing slug: {e}")
        return False
    
    # Check if slug history was created
    print("\n3. Checking slug history...")
    try:
        history = OrganizationSlugHistory.objects.filter(old_slug=old_slug, organization=org)
        if history.exists():
            print(f"   ✓ Slug history created: {history.first().old_slug} -> {org.slug}")
        else:
            print(f"   ✗ No slug history found for old slug: {old_slug}")
            return False
    except Exception as e:
        print(f"   Error checking slug history: {e}")
        return False
    
    # Test the redirect functionality using Django test client
    print("\n4. Testing redirect functionality...")
    try:
        client = Client()
        old_url = f'/organization/{old_slug}/'
        expected_redirect_url = f'/organization/{new_slug}/'
        
        print(f"   Testing redirect from {old_url} to {expected_redirect_url}")
        
        response = client.get(old_url, follow=False)
        
        if response.status_code == 302:  # Redirect
            redirect_url = response.url
            print(f"   ✓ Redirect successful: {old_url} -> {redirect_url}")
            if new_slug in redirect_url:
                print("   ✓ Redirect points to correct new slug")
            else:
                print(f"   ✗ Redirect doesn't point to new slug. Got: {redirect_url}")
                return False
        else:
            print(f"   ✗ Expected redirect (302), got status: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"   Error testing redirect: {e}")
        return False
    
    # Test that new slug works directly
    print("\n5. Testing new slug direct access...")
    try:
        response = client.get(f'/organization/{new_slug}/', follow=True)
        if response.status_code == 200:
            print(f"   ✓ New slug accessible directly: {new_slug}")
        else:
            print(f"   ✗ New slug not accessible. Status: {response.status_code}")
            return False
    except Exception as e:
        print(f"   Error testing new slug: {e}")
        return False
    
    # Cleanup
    print("\n6. Cleaning up...")
    try:
        org.delete()
        print("   Test organization deleted")
    except Exception as e:
        print(f"   Error cleaning up: {e}")
    
    print("\n=== All tests passed! Organization slug redirect is working ===")
    return True

if __name__ == '__main__':
    success = test_organization_slug_redirect()
    sys.exit(0 if success else 1)
