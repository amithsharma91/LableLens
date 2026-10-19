import { BrowserRouter, Route, Routes } from 'react-router-dom';

import { ForgotPasswordPage } from './auth/ForgotPasswordPage';
import { ResetPasswordPage } from './auth/ResetPasswordPage';

function Home() {
  return (
    <main>
      <h1>LabelLens</h1>
      <p>
        <a href="/auth/forgot-password">Forgot your password?</a>
      </p>
    </main>
  );
}

function NotFound() {
  return (
    <main>
      <h1>Page not found</h1>
    </main>
  );
}

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/auth/forgot-password" element={<ForgotPasswordPage />} />
        <Route path="/auth/reset-password" element={<ResetPasswordPage />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </BrowserRouter>
  );
}