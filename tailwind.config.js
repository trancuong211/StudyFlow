module.exports = {
  content: ["./templates/**/*.html", "./apps/**/templates/**/*.html", "./static/js/**/*.js"],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#eff6ff",
          100: "#dbeafe",
          200: "#bfdbfe",
          300: "#93c5fd",
          400: "#60a5fa",
          500: "#3b82f6",
          600: "#2563eb",
          700: "#1d4ed8",
          800: "#1e40af",
          900: "#1e3a8a",
          950: "#172554",
        },
      },
      fontFamily: { sans: ["Inter", "system-ui", "sans-serif"] },
      borderRadius: { xl: "0.875rem", "2xl": "1.25rem" },
    },
  },
  plugins: [],
};
