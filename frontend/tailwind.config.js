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
        // Softer, more diffuse — the "expensive" look comes from light, layered shadows.
        card: "0 1px 2px rgba(16,24,40,.04), 0 1px 3px rgba(16,24,40,.05)",
        soft: "0 8px 28px -14px rgba(14,91,117,.16), 0 3px 10px -6px rgba(16,24,40,.05)",
        lift: "0 18px 44px -20px rgba(14,91,117,.22), 0 8px 18px -12px rgba(16,24,40,.08)",
        glow: "0 0 0 1px rgba(14,91,117,.05), 0 14px 44px -18px rgba(14,91,117,.26)",
        innerlg: "inset 0 1px 0 rgba(255,255,255,.07)",
      },
      backgroundImage: {
        sidebar: "linear-gradient(168deg, #0f6178 0%, #0c4658 56%, #0a3340 100%)",
        brand: "linear-gradient(135deg, #11627d 0%, #2391b0 100%)",
        "brand-soft": "linear-gradient(135deg, #eef7fa 0%, #dbeef3 100%)",
        mesh: "radial-gradient(900px 420px at 100% -8%, rgba(255,255,255,.10), transparent), radial-gradient(680px 520px at -10% 112%, rgba(255,255,255,.06), transparent)",
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
