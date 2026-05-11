/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        bg: "#0b0d12",
        panel: "#11141b",
        border: "#1e2230",
        muted: "#8a91a3",
        text: "#e6e8ee",
        accent: "#7c5cff",
        accent2: "#3ddc97",
        warn: "#ffb454",
        danger: "#ff5670",
      },
    },
  },
  plugins: [],
};
