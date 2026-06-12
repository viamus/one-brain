import { createTheme } from "@mui/material/styles";

export const theme = createTheme({
  palette: {
    mode: "light",
    primary: {
      main: "#12645f",
      contrastText: "#ffffff"
    },
    secondary: {
      main: "#6b4eff"
    },
    warning: {
      main: "#b7791f"
    },
    background: {
      default: "#f6f8fb",
      paper: "#ffffff"
    },
    text: {
      primary: "#17212b",
      secondary: "#536171"
    }
  },
  shape: {
    borderRadius: 8
  },
  typography: {
    fontFamily:
      'Inter, Roboto, "Helvetica Neue", Arial, "Noto Sans", sans-serif',
    h1: {
      fontSize: "1.5rem",
      fontWeight: 700,
      letterSpacing: 0
    },
    h2: {
      fontSize: "1.05rem",
      fontWeight: 700,
      letterSpacing: 0
    },
    button: {
      fontWeight: 700,
      letterSpacing: 0,
      textTransform: "none"
    }
  },
  components: {
    MuiButton: {
      styleOverrides: {
        root: {
          minHeight: 38
        }
      }
    },
    MuiCard: {
      styleOverrides: {
        root: {
          borderRadius: 8,
          boxShadow: "0 1px 2px rgba(16, 24, 40, 0.08)"
        }
      }
    }
  }
});
