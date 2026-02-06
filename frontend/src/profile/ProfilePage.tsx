import { useState, FormEvent } from "react";
import { useAuth } from "../auth/AuthContext";

export function ProfilePage() {
  const { user, updateProfile } = useAuth();
  const [programmingLevel, setProgrammingLevel] = useState(
    user?.programming_level ?? 3
  );
  const [mathsLevel, setMathsLevel] = useState(user?.maths_level ?? 3);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [message, setMessage] = useState("");

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    setMessage("");

    try {
      await updateProfile({
        programming_level: programmingLevel,
        maths_level: mathsLevel,
      });
      setMessage("Profile updated successfully!");
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Update failed");
    } finally {
      setIsSubmitting(false);
    }
  };

  if (!user) {
    return null;
  }

  return (
    <div className="max-w-md mx-auto">
      <div className="bg-white rounded-lg shadow-md p-8">
        <h1 className="text-2xl font-bold text-center mb-6">Profile</h1>

        {message && (
          <div
            className={`px-4 py-3 rounded mb-4 ${
              message.includes("success")
                ? "bg-green-100 border border-green-400 text-green-700"
                : "bg-red-100 border border-red-400 text-red-700"
            }`}
          >
            {message}
          </div>
        )}

        <div className="space-y-4 mb-6">
          <div>
            <span className="text-sm font-medium text-gray-700">Email:</span>
            <p className="text-gray-900">{user.email}</p>
          </div>
          <div>
            <span className="text-sm font-medium text-gray-700">
              Member since:
            </span>
            <p className="text-gray-900">
              {new Date(user.created_at).toLocaleDateString()}
            </p>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label
              htmlFor="programmingLevel"
              className="block text-sm font-medium text-gray-700 mb-1"
            >
              Programming Level: {programmingLevel}
            </label>
            <input
              type="range"
              id="programmingLevel"
              min="1"
              max="5"
              value={programmingLevel}
              onChange={(e) => setProgrammingLevel(parseInt(e.target.value))}
              className="w-full"
            />
            <div className="flex justify-between text-xs text-gray-500">
              <span>Beginner</span>
              <span>Expert</span>
            </div>
          </div>

          <div>
            <label
              htmlFor="mathsLevel"
              className="block text-sm font-medium text-gray-700 mb-1"
            >
              Mathematics Level: {mathsLevel}
            </label>
            <input
              type="range"
              id="mathsLevel"
              min="1"
              max="5"
              value={mathsLevel}
              onChange={(e) => setMathsLevel(parseInt(e.target.value))}
              className="w-full"
            />
            <div className="flex justify-between text-xs text-gray-500">
              <span>Beginner</span>
              <span>Expert</span>
            </div>
          </div>

          <button
            type="submit"
            disabled={isSubmitting}
            className="w-full bg-blue-600 text-white py-2 px-4 rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
          >
            {isSubmitting ? "Saving..." : "Save Changes"}
          </button>
        </form>
      </div>
    </div>
  );
}
