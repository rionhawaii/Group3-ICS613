import { useEffect, useState } from 'react';

import type {
  ChangeEvent,
  FormEvent,
} from 'react';

import {
  Navigate,
  useNavigate,
} from 'react-router-dom';

import { authApi } from '../api/auth';
import {
  ApiRequestError,
  clearTokens,
  hasTokens,
} from '../api/client';

const maxDisplayNameLength = 40;
const maxNeighborhoodLength = 255;
const maxPhotoSizeBytes = 5 * 1024 * 1024;

const allowedPhotoTypes = [
  'image/jpeg',
  'image/png',
  'image/webp',
];

const mockAuthKey = 'mockAuthStatus'; // pragma: allowlist secret -- localStorage key name, not a credential
const mockProfileKey = 'mockUserProfile';

const isMockMode =
  import.meta.env.VITE_USE_MOCKS === 'true';

interface CachedProfile {
  userId?: string;
  displayName?: string;
  bio?: string;
  neighborhood?: string;
  photoFileName?: string;
  profileSetupComplete?: boolean;
}

/**
 * Read the temporary frontend profile cache safely.
 *
 * The backend remains authoritative for fields saved through PUT /auth/me.
 * This cache preserves mock compatibility and records that setup was
 * completed for a specific authenticated user.
 */
function readCachedProfile(): CachedProfile | null {
  const savedProfile = localStorage.getItem(mockProfileKey);

  if (!savedProfile) {
    return null;
  }

  try {
    return JSON.parse(savedProfile) as CachedProfile;
  } catch {
    return null;
  }
}

/**
 * ProfileSetupPage
 *
 * Issue #32 / User Story 5:
 * - Requires a display name.
 * - Supports optional bio and neighborhood.
 * - Validates an optional profile-photo selection.
 * - Verifies authenticated API sessions through GET /auth/me.
 * - Saves supported profile fields through PUT /auth/me.
 * - Uploads a selected profile photo through POST /auth/me/photo.
 * - Redirects unauthenticated users to Login.
 * - Redirects a user who already completed setup to Edit Profile.
 * - Redirects to Dashboard only after a successful save.
 *
 * Backend limitations:
 * - UserProfile does not expose an explicit profile-completed field.
 */
function ProfileSetupPage() {
  const navigate = useNavigate();

  const hasApiSession = hasTokens();

  const hasMockSession =
    isMockMode &&
    localStorage.getItem(mockAuthKey) === 'logged-in';

  const isAuthenticated =
    hasApiSession || hasMockSession;

  const [displayName, setDisplayName] = useState('');
  const [bio, setBio] = useState('');
  const [neighborhood, setNeighborhood] = useState('');
  const [photoFileName, setPhotoFileName] = useState('');
  const [selectedPhotoFile, setSelectedPhotoFile] =
    useState<File | null>(null);

  const [errorMessage, setErrorMessage] = useState('');
  const [successMessage, setSuccessMessage] = useState('');

  const [isCheckingProfile, setIsCheckingProfile] =
    useState(true);

  const [isSaving, setIsSaving] = useState(false);

  const [redirectToLogin, setRedirectToLogin] =
    useState(!isAuthenticated);

  const [redirectToEdit, setRedirectToEdit] =
    useState(false);

  /**
   * Validate the session, load the current backend profile, and determine
   * whether this specific user has already completed frontend profile setup.
   */
  useEffect(() => {
    let ignoreResult = false;

    async function initializeProfile() {
      if (!isAuthenticated) {
        /**
         * Remove a stale compatibility flag when the real application
         * no longer has an authenticated API session.
         */
        if (!isMockMode) {
          localStorage.removeItem(mockAuthKey);

          window.dispatchEvent(
            new Event('mock-auth-change'),
          );
        }

        if (!ignoreResult) {
          setRedirectToLogin(true);
          setIsCheckingProfile(false);
        }

        return;
      }

      const cachedProfile = readCachedProfile();

      /**
       * Temporary mock-only compatibility.
       *
       * Mock sessions do not have a backend user ID, so the existing
       * frontend completion marker is used.
       */
      if (!hasApiSession) {
        if (!ignoreResult && cachedProfile) {
          setDisplayName(cachedProfile.displayName ?? '');
          setBio(cachedProfile.bio ?? '');
          setNeighborhood(cachedProfile.neighborhood ?? '');
          setPhotoFileName(cachedProfile.photoFileName ?? '');

          if (cachedProfile.profileSetupComplete) {
            setRedirectToEdit(true);
          }
        }

        if (!ignoreResult) {
          setIsCheckingProfile(false);
        }

        return;
      }

      try {
        const currentUser = await authApi.me();

        if (ignoreResult) {
          return;
        }

        /**
         * Completion markers are matched to the authenticated backend user
         * so another account cannot inherit a stale browser marker.
         */
        const setupAlreadyCompleted =
          cachedProfile?.profileSetupComplete === true &&
          cachedProfile.userId === currentUser.id;

        if (setupAlreadyCompleted) {
          setRedirectToEdit(true);
          return;
        }

        setDisplayName(
          currentUser.full_name ??
          cachedProfile?.displayName ??
          '',
        );

        setBio(
          currentUser.bio ??
          cachedProfile?.bio ??
          '',
        );

        setNeighborhood(
          currentUser.neighborhood ??
          cachedProfile?.neighborhood ??
          '',
        );

        setPhotoFileName(
          cachedProfile?.photoFileName ?? '',
        );
      } catch (error) {
        if (ignoreResult) {
          return;
        }

        if (
          error instanceof ApiRequestError &&
          error.status === 401
        ) {
          clearTokens();
          localStorage.removeItem(mockAuthKey);

          window.dispatchEvent(
            new Event('auth-change'),
          );

          window.dispatchEvent(
            new Event('mock-auth-change'),
          );

          setRedirectToLogin(true);
          return;
        }

        setErrorMessage(
          error instanceof ApiRequestError
            ? error.detail
            : 'Unable to load your profile. You may still enter your profile information and try saving.',
        );
      } finally {
        if (!ignoreResult) {
          setIsCheckingProfile(false);
        }
      }
    }

    void initializeProfile();

    return () => {
      ignoreResult = true;
    };
  }, [hasApiSession, isAuthenticated]);

  /**
   * Validate the optional profile-photo selection.
   *
   * Invalid files are cleared without changing display name, bio,
   * or neighborhood state.
   */
  function handlePhotoChange(
    event: ChangeEvent<HTMLInputElement>,
  ) {
    setErrorMessage('');
    setSuccessMessage('');

    const selectedFile = event.target.files?.[0];

    if (!selectedFile) {
      setPhotoFileName('');
      setSelectedPhotoFile(null);
      return;
    }

    if (!allowedPhotoTypes.includes(selectedFile.type)) {
      setPhotoFileName('');
      setSelectedPhotoFile(null);
      event.target.value = '';

      setErrorMessage(
        'Profile photo must be a JPG, PNG, or WebP image.',
      );

      return;
    }

    if (selectedFile.size > maxPhotoSizeBytes) {
      setPhotoFileName('');
      setSelectedPhotoFile(null);
      event.target.value = '';

      setErrorMessage(
        'Profile photo must be 5 MB or smaller.',
      );

      return;
    }

    setPhotoFileName(selectedFile.name);
    setSelectedPhotoFile(selectedFile);
  }

  /**
   * Save the supported profile fields.
   *
   * Real API sessions use PUT /auth/me. Mock-only sessions retain
   * frontend demo compatibility.
   */
  async function handleSubmit(
    event: FormEvent<HTMLFormElement>,
  ) {
    event.preventDefault();

    if (isSaving) {
      return;
    }

    setErrorMessage('');
    setSuccessMessage('');

    const normalizedDisplayName =
      displayName.trim();

    const normalizedBio =
      bio.trim();

    const normalizedNeighborhood =
      neighborhood.trim();

    if (!normalizedDisplayName) {
      setErrorMessage(
        'Display name is required.',
      );

      return;
    }

    if (
      normalizedDisplayName.length >
      maxDisplayNameLength
    ) {
      setErrorMessage(
        `Display name must be ${maxDisplayNameLength} characters or fewer.`,
      );

      return;
    }

    if (
      normalizedNeighborhood.length >
      maxNeighborhoodLength
    ) {
      setErrorMessage(
        `Neighborhood must be ${maxNeighborhoodLength} characters or fewer.`,
      );

      return;
    }

    setIsSaving(true);

    try {
      let savedUserId: string | undefined;
      let savedPhotoUrl: string | null = null;

      if (hasApiSession) {
        let savedProfile =
          await authApi.updateMe({
            full_name: normalizedDisplayName,
            bio: normalizedBio || null,
            neighborhood:
              normalizedNeighborhood || null,
          });

        if (selectedPhotoFile) {
          savedProfile =
            await authApi.uploadProfilePhoto(
              selectedPhotoFile,
            );
        }

        savedUserId = savedProfile.id;
        savedPhotoUrl =
          savedProfile.photo_url ?? null;
      } else if (!hasMockSession) {
        setRedirectToLogin(true);
        return;
      }

      const cachedProfile: CachedProfile = {
        userId: savedUserId,
        displayName: normalizedDisplayName,
        bio: normalizedBio,
        neighborhood: normalizedNeighborhood,
        photoFileName,
        ...(hasApiSession
          ? { photoUrl: savedPhotoUrl }
          : {}),
        profileSetupComplete: true,
      };

      /**
       * For API sessions, cache failure must not override a successful
       * backend save. For mock-only sessions, localStorage is the save.
       */
      if (hasApiSession) {
        try {
          localStorage.setItem(
            mockProfileKey,
            JSON.stringify(cachedProfile),
          );
        } catch {
          // The backend profile save is authoritative.
        }
      } else {
        localStorage.setItem(
          mockProfileKey,
          JSON.stringify(cachedProfile),
        );
      }

      setSuccessMessage(
        'Profile setup complete. Redirecting to dashboard...',
      );

      // Give the success message a moment to actually paint before leaving
      // the page -- navigating in the same tick as the state update meant
      // the message was set but never visibly rendered.
      window.setTimeout(() => {
        navigate('/dashboard', {
          replace: true,
        });
      }, 800);
    } catch (error) {
      if (
        error instanceof ApiRequestError &&
        error.status === 401
      ) {
        clearTokens();
        localStorage.removeItem(mockAuthKey);

        window.dispatchEvent(
          new Event('auth-change'),
        );

        window.dispatchEvent(
          new Event('mock-auth-change'),
        );

        setRedirectToLogin(true);
        return;
      }

      setErrorMessage(
        error instanceof ApiRequestError
          ? error.detail
          : error instanceof Error &&
              error.message.trim()
            ? error.message
            : 'Unable to save your profile. Please try again.',
      );
    } finally {
      setIsSaving(false);
    }
  }

  if (redirectToLogin) {
    return (
      <Navigate
        to="/login"
        replace
      />
    );
  }

  if (redirectToEdit) {
    return (
      <Navigate
        to="/profile/edit"
        replace
      />
    );
  }

  if (isCheckingProfile) {
    return (
      <section className="page-section">
        <div className="empty-state-card">
          <p className="eyebrow">
            Profile Setup
          </p>

          <h1>
            Checking your profile...
          </h1>

          <p>
            Confirming your authenticated member profile before setup.
          </p>
        </div>
      </section>
    );
  }

  return (
    <section className="page-section">
      <div className="page-header">
        <div>
          <p className="eyebrow">
            Profile Setup
          </p>

          <h1>
            Set Up Your Profile
          </h1>

          <p className="page-description">
            Complete your member profile before using the
            tool-sharing dashboard.
          </p>
        </div>
      </div>

      <div className="profile-layout">
        <form
          className="profile-card"
          onSubmit={handleSubmit}
          noValidate
          aria-busy={isSaving}
        >
          <h2>
            Member Profile
          </h2>

          <label htmlFor="profile-display-name">
            Display Name

            <input
              id="profile-display-name"
              type="text"
              value={displayName}
              onChange={(event) =>
                setDisplayName(event.target.value)
              }
              maxLength={maxDisplayNameLength + 10}
              required
              disabled={isSaving}
            />
          </label>

          <p className="auth-helper-text">
            {displayName.trim().length}/
            {maxDisplayNameLength} characters
          </p>

          <label htmlFor="profile-bio">
            Short Bio

            <textarea
              id="profile-bio"
              value={bio}
              onChange={(event) =>
                setBio(event.target.value)
              }
              rows={4}
              placeholder="Tell neighbors a little about yourself."
              disabled={isSaving}
            />
          </label>

          <label htmlFor="profile-neighborhood">
            Neighborhood or Location

            <input
              id="profile-neighborhood"
              type="text"
              value={neighborhood}
              onChange={(event) =>
                setNeighborhood(event.target.value)
              }
              maxLength={maxNeighborhoodLength}
              placeholder="For example: Manoa, Kaimuki, or Honolulu"
              disabled={isSaving}
            />
          </label>

          <p className="auth-helper-text">
            Optional. This location may appear on your public member profile.
          </p>

          <label htmlFor="profile-photo">
            Profile Photo

            <input
              id="profile-photo"
              type="file"
              accept="image/jpeg,image/png,image/webp"
              onChange={handlePhotoChange}
              disabled={isSaving}
            />
          </label>

          <p className="auth-helper-text">
            Accepted photo types: JPG, PNG, or WebP. Maximum
            size: 5 MB. The selected file is uploaded when
            you save your profile.
          </p>

          <button
            className="primary-button"
            type="submit"
            disabled={isSaving}
          >
            {isSaving
              ? 'Saving Profile...'
              : 'Save Profile'}
          </button>

          <div aria-live="polite">
            {errorMessage && (
              <p
                className="form-error"
                role="alert"
              >
                {errorMessage}
              </p>
            )}

            {successMessage && (
              <p className="form-success">
                {successMessage}
              </p>
            )}
          </div>
        </form>

        <aside className="profile-card profile-preview-card">
          <h2>
            Profile Preview
          </h2>

          <div className="profile-avatar-preview">
            {photoFileName
              ? photoFileName.slice(0, 1).toUpperCase()
              : '\u{1F464}'}
          </div>

          <h3>
            {displayName.trim() ||
              'Display Name Required'}
          </h3>

          <p>
            {bio.trim() ||
              'Your short bio will appear here.'}
          </p>

          <dl className="public-profile-detail-list">
            <div>
              <dt>
                Neighborhood
              </dt>

              <dd>
                {neighborhood.trim() ||
                  'Not provided'}
              </dd>
            </div>
          </dl>

          <p className="auth-helper-text">
            Photo file:{' '}
            {photoFileName || 'No photo selected'}
          </p>
        </aside>
      </div>
    </section>
  );
}

export default ProfileSetupPage;
