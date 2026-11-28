module.exports = {
  content: ["./templates/**/*.html", "./apps/**/templates/**/*.html", "./static/js/**/*.js"],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#eef5f6",
          100: "#dde9ec",
          200: "#c4d9df",
          300: "#9fc2cb",
          400: "#6f9fae",
          500: "#4a7f90",
          600: "#2b5d6b",
          700: "#234953",
          800: "#1c3a42",
          900: "#162e34",
          950: "#0f2024",
        },
        accent: {
          50: "#f9efeb",
          100: "#f3e4dd",
          200: "#e7c8ba",
          300: "#d9a78f",
          400: "#cd8666",
          500: "#c06b4e",
          600: "#a85a3f",
          700: "#8a4934",
          800: "#6e3b2b",
          900: "#5a3125",
          950: "#321a14",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        heading: ["Fraunces", "Georgia", "serif"],
      },
      borderRadius: { xl: "0.875rem", "2xl": "1.25rem" },
    },
  },
  plugins: [],
};
