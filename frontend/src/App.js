import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import "./styles/common.css";

import AppProviders from "./app/AppProviders";
import Header from "./components/layout/Header";
import BottomNav from "./components/layout/BottomNav";
import ProtectedRoute from "./components/common/ProtectedRoute";
import ScrollToTop from "./components/common/ScrollToTop";

import Home from "./pages/Home";
import ResultPage from "./pages/menuscan/ResultPage";
import Login from "./pages/auth/Login";

import Profile from "./pages/member/Profile";
import EditProfile from "./pages/member/EditProfile";

import CommunityDetail from "./pages/community/CommunityDetail";
import CommunityCreate from "./pages/community/CommunityCreate";
import Community from "./pages/community/Community";

import ReviewList from "./pages/review/ReviewList";
import ReviewDetail from "./pages/review/ReviewDetail";
import ReviewCreate from "./pages/review/ReviewCreate";
import ReviewEdit from "./pages/review/ReviewEdit";

// test
import Register from "./pages/auth/Register";

// admin 추가
import Admin from "./pages/admin/Admin_new";

export default function App() {
  return (
    <AppProviders>
      <BrowserRouter>
        <ScrollToTop />
        <Header />

        <main className="app-main">
        <Routes>
          {/* 공개 페이지 (로그인 불필요) */}
          <Route path="/" element={<Home />} />
          <Route path="/login" element={<Login />} />
          <Route path="/result" element={<ResultPage />} />
          <Route path="/register" element={<Register />} />

          {/* 커뮤니티 - 목록/상세 공개, 작성/수정은 로그인 필수 */}
          <Route path="/community" element={<Community />} />
          <Route path="/community/new" element={<ProtectedRoute excludeRoles={["ADMIN"]}><CommunityCreate /></ProtectedRoute>} />
          {/* <Route path="/community/:id/edit" element={<ProtectedRoute excludeRoles={["ADMIN"]}><CommunityEdit /></ProtectedRoute>} /> */}
          <Route path="/community/:id" element={<CommunityDetail />} />

          {/* 리뷰 - 목록/상세 공개, 작성/수정은 로그인 필수 */}
          <Route path="/review" element={<ReviewList />} />
          <Route path="/review/new" element={<ProtectedRoute excludeRoles={["ADMIN"]}><ReviewCreate /></ProtectedRoute>} />
          <Route path="/review/:id/edit" element={<ProtectedRoute excludeRoles={["ADMIN"]}><ReviewEdit /></ProtectedRoute>} />
          <Route path="/review/:id" element={<ReviewDetail />} />

          {/* 관리자 페이지 */}
          <Route
            path="/admin"
            element={
              <ProtectedRoute roles={["ADMIN"]}>
                <Admin />
              </ProtectedRoute>
            }
          />

          {/* 비공개 페이지 (로그인 필수) */}
          {/* member */}
          <Route
            path="/member/profile"
            element={
              <ProtectedRoute excludeRoles={["ADMIN"]}>
                <Profile />
              </ProtectedRoute>
            }
          />
          <Route
            path="/member/edit"
            element={
              <ProtectedRoute excludeRoles={["ADMIN"]}>
                <EditProfile />
              </ProtectedRoute>
            }
          />



          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        </main>

        <BottomNav />
      </BrowserRouter>
    </AppProviders>
  );
}