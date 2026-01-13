/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      fontFamily: {
        serif: ["Noto Serif SC", "serif"],
        sans: ["Source Sans 3", "Noto Serif SC", "sans-serif"],
      },
      colors: {
        ink: "#0f172a",
        muted: "#475569",
      },
      boxShadow: {
        panel: "0 18px 40px rgba(15, 23, 42, 0.18)",
      },
    },
  },
  plugins: [],
};
