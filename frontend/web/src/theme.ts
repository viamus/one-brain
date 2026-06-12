import { createTheme } from "@mui/material/styles";

export const theme = createTheme({
  palette: {
    mode: "dark",
    primary: {
      main: "#f97316",
      contrastText: "#160a03"
    },
    secondary: {
      main: "#8b7cff"
    },
    warning: {
      main: "#f59e0b"
    },
    background: {
      default: "#070b12",
      paper: "#0d1420"
    },
    text: {
      primary: "#e6edf7",
      secondary: "#91a4bd"
    },
    divider: "#1d2a3a",
    action: {
      hover: "rgba(249, 115, 22, 0.1)",
      selected: "rgba(249, 115, 22, 0.18)"
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
          border: "1px solid #1d2a3a",
          borderRadius: 8,
          backgroundImage: "none",
          boxShadow: "0 18px 48px rgba(0, 0, 0, 0.28)"
        }
      }
    },
    MuiAppBar: {
      styleOverrides: {
        root: {
          backgroundImage: "none"
        }
      }
    },
    MuiChip: {
      styleOverrides: {
        root: {
          backgroundColor: "#172235",
          color: "#d7e3f3"
        }
      }
    },
    MuiOutlinedInput: {
      styleOverrides: {
        root: {
          backgroundColor: "#0a111c"
        }
      }
    }
  }
});
