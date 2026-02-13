import React, { useContext, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { AuthContext } from "../../context/AuthContext";
import { getJwtRole } from "../../utils/jwt";
import "../../styles/Register.css";

export default function Login() {
  const { authActions } = useContext(AuthContext);
  const nav = useNavigate();
  const [searchParams] = useSearchParams();

  // URL param으로 전달된 안내 메시지 처리
  const paramMsg = searchParams.get("msg");
  const guideMsg = paramMsg === "login_required" ? "Please Sign in" : null;

  const [form, setForm] = useState({
    email: "",
    password: "",
  });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const onChange = (e) => {
    const { name, value } = e.target;
    setForm((p) => ({ ...p, [name]: value }));
  };

  const onSubmit = async (e) => {
    e.preventDefault();
    setError("");

    if (!form.email.trim() || !form.password) {
      setError("Please enter your email and password.");
      return;
    }

    setLoading(true);
      try {
        const ok = await authActions.login(form.email.trim(), form.password);

        if (ok) {
          const token = sessionStorage.getItem("access_token");
          const role = getJwtRole(token);
          nav(role === "ADMIN" ? "/admin" : "/");
        } else {
          setError("Please check your email or password");
        }
      } catch (err) {
        const status = err?.response?.status;
        if (status === 500 || status === 401 || status === 400) {
          setError("Please check your email or password");
        } else {
          setError("Login failed");
        }
      } finally {
        setLoading(false);
      }
    };

  return (
    <div className="RegisterPage">
      <div className="RegisterHeader">
        <h2>Login</h2>
      </div>

      {guideMsg && <div className="RegisterMsg ok">{guideMsg}</div>}
      {error && <div className="RegisterMsg err">{error}</div>}

      <form className="card RegisterForm" onSubmit={onSubmit}>
        <div className="row">
          <label>Email</label>
          <input
            name="email"
            value={form.email}
            onChange={onChange}
            placeholder="email@example.com"
            autoComplete="email"
          />
        </div>

        <div className="row">
          <label>Password</label>
          <input
            name="password"
            value={form.password}
            onChange={onChange}
            type="password"
            placeholder="password"
            autoComplete="current-password"
          />
        </div>

        <div className="RegisterActions">
          <button type="button" className="loginActionBtn" onClick={() => nav("/register")}>
            Sign up
          </button>
          <button type="submit" disabled={loading}>
            {loading ? "Logging in..." : "Login"}
          </button>
        </div>
      </form>
    </div>
  );
}
