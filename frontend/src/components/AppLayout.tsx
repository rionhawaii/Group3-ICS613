import { useEffect, useState } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/useAuth';
import { notificationsApi } from '../api/notifications';

const USE_MOCKS = import.meta.env.VITE_USE_MOCKS === 'true';

function AppLayout() {
  const navigate = useNavigate();
  const { user, isAuthenticated, logout } = useAuth();
  const [unreadCount, setUnreadCount] = useState(0);

  // Fetch unread notification count.
  useEffect(() => {
    if (!isAuthenticated) return;

    let convergeTimer: ReturnType<typeof setTimeout> | undefined;

    const fetchUnread = async () => {
      try {
        const data = await notificationsApi.list({ page_size: 1 });
        setUnreadCount(data.unread_count);
      } catch {
        // Silently handle — notifications may not be loaded.
      }
    };

    const handler = () => {
      fetchUnread();
      // Re-verify shortly after so the badge converges even if the first
      // fetch raced the read-state change that fired the event.
      if (convergeTimer) clearTimeout(convergeTimer);
      convergeTimer = setTimeout(fetchUnread, 1000);
    };

    fetchUnread();
    window.addEventListener('auth-change', handler);
    return () => {
      if (convergeTimer) clearTimeout(convergeTimer);
      window.removeEventListener('auth-change', handler);
    };
  }, [isAuthenticated]);

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  const getNavLinkClass = ({ isActive }: { isActive: boolean }) =>
    isActive ? 'nav-link active' : 'nav-link';

  return (
    <div className="app-shell">
      <header className="app-header">
        <div>
          <p className="eyebrow">ICS 613 Group 3</p>
          <h1>Neighborhood Tool Sharing</h1>
        </div>

        <nav className="app-nav" aria-label="Main navigation">
          {isAuthenticated ? (
            <>
              {USE_MOCKS && (
                <span className="mock-banner">MOCK MODE</span>
              )}

              <span className="nav-user-greeting">
                {user?.full_name || user?.email || 'User'}
              </span>

              <NavLink className={getNavLinkClass} to="/dashboard">
                Dashboard
              </NavLink>

              <div className="nav-dropdown">
                <NavLink className="nav-link nav-dropdown-toggle" to="/tools">
                  Browse Tools
                </NavLink>
                <div className="nav-dropdown-menu">
                  <NavLink className="nav-dropdown-item" to="/tools">
                    Available Tools
                  </NavLink>
                  <NavLink className="nav-dropdown-item" to="/tools?view=returned">
                    Returned Tools
                  </NavLink>
                  <NavLink className="nav-dropdown-item" to="/tools/mine">
                    My Tools
                  </NavLink>
                  <NavLink className="nav-dropdown-item" to="/tools/new">
                    Add New Tools
                  </NavLink>
                </div>
              </div>

              <NavLink className={getNavLinkClass} to="/reservations">
                Reservations
              </NavLink>

              <NavLink className={getNavLinkClass} to="/reviews/history">
                Review History
              </NavLink>

              <NavLink className={getNavLinkClass} to="/notifications">
                <span className="notification-nav-label">
                  Notifications
                  {unreadCount > 0 && (
                    <span className="nav-notification-badge">
                      {unreadCount}
                    </span>
                  )}
                </span>
              </NavLink>

              <NavLink className={getNavLinkClass} to="/profile/edit">
                Profile
              </NavLink>

              <NavLink className={getNavLinkClass} to="/account/delete">
                Delete Account
              </NavLink>

              {user?.is_admin && (
                <>
                  <NavLink className={getNavLinkClass} to="/admin/members">
                    Admin Members
                  </NavLink>
                  <NavLink className={getNavLinkClass} to="/admin/invites">
                    Admin Invites
                  </NavLink>
                  <NavLink className={getNavLinkClass} to="/admin/listings">
                    Admin Listings
                  </NavLink>
                  <NavLink className={getNavLinkClass} to="/admin/reported">
                    Reported Listings
                  </NavLink>
                  <NavLink className={getNavLinkClass} to="/admin/categories">
                    Categories
                  </NavLink>
                  <NavLink className={getNavLinkClass} to="/admin/reservations">
                    Admin Reservations
                  </NavLink>
                  <NavLink className={getNavLinkClass} to="/admin/reports">
                    Admin Reports
                  </NavLink>
                  <NavLink className={getNavLinkClass} to="/admin/moderation">
                    Moderation
                  </NavLink>
                  <NavLink className={getNavLinkClass} to="/admin/moderation/reports">
                    Moderation Reports
                  </NavLink>
                </>
              )}

              <button
                className="nav-link nav-button"
                type="button"
                onClick={handleLogout}
              >
                Logout
              </button>
            </>
          ) : (
            <>
              <NavLink className={getNavLinkClass} to="/login">
                Login
              </NavLink>
              <NavLink className={getNavLinkClass} to="/register">
                Register
              </NavLink>
            </>
          )}
        </nav>
      </header>

      <main className="app-main">
        <Outlet />
      </main>
    </div>
  );
}

export default AppLayout;
