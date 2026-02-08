import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

export function Navbar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = async () => {
    await logout();
    navigate("/login");
  };

  return (
    <nav className="bg-brand shadow-md">
      <div className="container mx-auto px-4">
        <div className="flex justify-between items-center h-16">
          <Link to="/" className="text-xl font-bold text-accent-light">
            Guided Cursor
          </Link>

          <div className="flex items-center space-x-4">
            {user ? (
              <>
                <Link
                  to="/chat"
                  className="text-gray-200 hover:text-accent-light"
                >
                  Chat
                </Link>
                <span
                  className="text-gray-500 cursor-not-allowed"
                  title="Coming in Phase 3"
                >
                  Modules
                </span>
                <Link
                  to="/profile"
                  className="text-gray-200 hover:text-accent-light"
                >
                  Profile
                </Link>
                <button
                  onClick={handleLogout}
                  className="bg-accent text-brand px-4 py-2 rounded-md hover:bg-accent-dark"
                >
                  Logout
                </button>
              </>
            ) : (
              <>
                <Link
                  to="/login"
                  className="text-gray-200 hover:text-accent-light"
                >
                  Login
                </Link>
                <Link
                  to="/register"
                  className="bg-accent text-brand px-4 py-2 rounded-md hover:bg-accent-dark"
                >
                  Register
                </Link>
              </>
            )}
          </div>
        </div>
      </div>
    </nav>
  );
}
