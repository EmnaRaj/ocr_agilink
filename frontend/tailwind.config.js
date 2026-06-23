/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Agilink Group brand petrol-blue (from the logo) + a full scale
        agilink: {
          50: "#eef7fa",
          100: "#d3ebf1",
          200: "#a9d6e2",
          300: "#73b9cd",
          400: "#3f96b1",
          500: "#217a96",
          600: "#0e5b75",
          700: "#0d4d63",
          800: "#103f51",
          900: "#0e3543",
          950: "#07222c",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "Segoe UI", "Roboto", "sans-serif"],
      },
      boxShadow: {
        card: "0 1px 3px rgba(16,24,40,.07), 0 1px 2px rgba(16,24,40,.04)",
        soft: "0 6px 24px -10px rgba(14,91,117,.18), 0 2px 8px -4px rgba(16,24,40,.06)",
        glow: "0 0 0 1px rgba(14,91,117,.06), 0 12px 40px -16px rgba(14,91,117,.30)",
        innerlg: "inset 0 1px 0 rgba(255,255,255,.06)",
      },
      backgroundImage: {
        sidebar: "linear-gradient(170deg, #0e5b75 0%, #0c4255 55%, #0a3140 100%)",
        brand: "linear-gradient(135deg, #0e5b75 0%, #1f86a4 100%)",
        "brand-soft": "linear-gradient(135deg, #eef7fa 0%, #d3ebf1 100%)",
        mesh: "radial-gradient(900px 400px at 100% -5%, rgba(33,122,150,.08), transparent), radial-gradient(700px 500px at -10% 110%, rgba(14,91,117,.06), transparent)",
      },
      keyframes: {
        "fade-in": { "0%": { opacity: 0, transform: "translateY(6px)" }, "100%": { opacity: 1, transform: "none" } },
        "fade-in-fast": { "0%": { opacity: 0 }, "100%": { opacity: 1 } },
        blink: { "0%,100%": { opacity: 1 }, "50%": { opacity: 0 } },
        "scale-in": { "0%": { opacity: 0, transform: "scale(.97)" }, "100%": { opacity: 1, transform: "scale(1)" } },
      },
      animation: {
        "fade-in": "fade-in .35s cubic-bezier(.2,.7,.2,1)",
        "fade-in-fast": "fade-in-fast .2s ease-out",
        blink: "blink 1s step-end infinite",
        "scale-in": "scale-in .25s cubic-bezier(.2,.7,.2,1)",
      },
    },
  },
  plugins: [],
};
