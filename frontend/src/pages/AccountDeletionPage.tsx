import { useCallback, useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { Link, Navigate, useNavigate } from 'react-router-dom';

import { authApi } from '../api/auth';
import { reservationsApi } from '../api/reservations';
import { useAuth } from '../context/useAuth';
import { ApiRequestError } from '../api/client';

const requiredConfirmationText = 'DELETE';

function AccountDeletionPage() {
  const navigate = useNavigate();
  const { user, isLoading: authLoading, logout } = useAuth();

  const [confirmationText, setConfirmationText] = useState('');
  const [understandsDeletion, setUnderstandsDeletion] = useState(false);
  const [deleteReason, setDeleteReason] = useState('');
  const [errorMessage, setErrorMessage] = useState('');
  const [successMessage, setSuccessMessage] = useState('');
  const [isDeleting, setIsDeleting] = useState(false);

  // Check for active reservations
  const [activeReservations, setActiveReservations] = useState<number | null>(null);
  const [checkingReservations, setCheckingReservations] = useState(true);

  const checkActiveReservations = useCallback(async () => {
    if (!user) return;
    setCheckingReservations(true);
    try {
      // Backend only supports role='borrower'|'owner' and single state values.
      // Make parallel calls for each active state.
      const states = ['REQUESTED', 'APPROVED', 'PICKED_UP'] as const;
      const roles = ['borrower', 'owner'] as const;
      const results = await Promise.all(
        roles.flatMap((role) =>
          states.map((state) =>
            reservationsApi.list({ role, state, page_size: 1 })
              .then((d) => d.total)
              .catch(() => 0)
          )
        )
      );
      setActiveReservations(results.reduce((a, b) => a + b, 0));
    } catch {
      // If the API call fails, allow deletion to proceed
      setActiveReservations(0);
    } finally {
      setCheckingReservations(false);
    }
  }, [user]);

  useEffect(() => {
    checkActiveReservations();
  }, [checkActiveReservations]);

  const hasActiveReservations = (activeReservations ?? 0) > 0;

  function handleDeleteSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrorMessage('');
    setSuccessMessage('');

    if (hasActiveReservations) {
      setErrorMessage(
        'Account deletion is blocked because you have active reservations. Please cancel, complete, or return all active reservations before deleting your account.',
      );
      return;
    }

    if (confirmationText.trim() !== requiredConfirmationText) {
      setErrorMessage('Please type DELETE to confirm account deletion.');
      return;
    }

    if (!understandsDeletion) {
      setErrorMessage('Please confirm that you understand this action cannot be undone.');
      return;
    }

    // We'll use an IIFE for the async deletion
    (async () => {
      setIsDeleting(true);
      try {
        await authApi.deleteMe();
        setSuccessMessage(
          'Your account deletion request was submitted. You will be redirected to Login.',
        );
        // Log out after a short delay
        window.setTimeout(async () => {
          await logout();
          navigate('/login');
        }, 900);
      } catch (err: unknown) {
        const msg = err instanceof ApiRequestError ? err.detail : 'Deletion request failed.';
        setErrorMessage(msg);
      } finally {
        setIsDeleting(false);
      }
    })();
  }

  if (authLoading || checkingReservations) {
    return (
      <section className="page-section">
        <div className="page-header"><h1>Loading...</h1></div>
      </section>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  return (
    <section className="page-section">
      <div className="page-header">
        <div>
          <p className="eyebrow">Account Settings</p>
          <h1>Delete Account</h1>
          <p className="page-description">
            Review active reservation restrictions before deleting your account.
          </p>
        </div>
        <Link className="secondary-link header-action-link" to="/profile/edit">
          Back to Profile
        </Link>
      </div>

      <div className="account-deletion-layout">
        <form className="account-deletion-card" onSubmit={handleDeleteSubmit} noValidate>
          <h2>Delete Your Account</h2>

          <div className="deletion-warning-panel">
            <h3>Warning</h3>
            <p>
              Account deletion is a serious action. Your profile, account access, and
              account-related information may no longer be available after deletion.
            </p>
          </div>

          {hasActiveReservations && (
            <div className="active-reservation-block">
              <h3>Account deletion is currently blocked</h3>
              <p>
                You cannot delete your account while you have active reservations.
                Please cancel, complete, or return all active reservations first.
              </p>
              <Link className="secondary-link narrow-link" to="/reservations">
                View Reservations
              </Link>
            </div>
          )}

          <label htmlFor="delete-reason">
            Reason for Deleting Account (Optional)
            <textarea
              id="delete-reason"
              value={deleteReason}
              onChange={(event) => setDeleteReason(event.target.value)}
              rows={4}
              placeholder="Optional: tell us why you are deleting your account."
            />
          </label>

          <label htmlFor="delete-confirmation">
            Type DELETE to Confirm
            <input
              id="delete-confirmation"
              type="text"
              value={confirmationText}
              onChange={(event) => setConfirmationText(event.target.value)}
              placeholder="DELETE"
              disabled={hasActiveReservations}
            />
            {hasActiveReservations && (
              <span className="field-disabled-hint">
                Disabled — you have active reservations. Cancel or complete them first.
              </span>
            )}
          </label>

          <label className="checkbox-row" htmlFor="understand-deletion">
            <input
              id="understand-deletion"
              type="checkbox"
              checked={understandsDeletion}
              onChange={(event) => setUnderstandsDeletion(event.target.checked)}
              disabled={hasActiveReservations}
            />
            I understand this action cannot be undone.
          </label>
          {hasActiveReservations && (
            <span className="field-disabled-hint">
              Disabled — you have active reservations. Cancel or complete them first.
            </span>
          )}

          <button
            className="danger-action-button"
            type="submit"
            disabled={hasActiveReservations || isDeleting}
          >
            {isDeleting ? 'Deleting...' : 'Delete Account'}
          </button>

          {errorMessage && <p className="form-error">{errorMessage}</p>}
          {successMessage && <p className="form-success">{successMessage}</p>}
        </form>

        <aside className="account-deletion-card">
          <h2>Deletion Checklist</h2>
          <ul className="deletion-checklist">
            <li>Return or cancel all active reservations.</li>
            <li>Confirm you understand deletion cannot be undone.</li>
            <li>Type DELETE before submitting the request.</li>
          </ul>
        </aside>
      </div>
    </section>
  );
}

export default AccountDeletionPage;
