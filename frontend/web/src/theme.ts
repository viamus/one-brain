import { createTheme } from "@mui/material/styles";

export const theme = createTheme({
  palette: {
    mode: "dark",
    primary: {
      main: "#D97757",
      contrastText: "#251713"
    },
    secondary: {
      main: "#B8694D"
    },
    warning: {
      main: "#E1A34A"
    },
    background: {
      default: "#0E0F0D",
      paper: "#171816"
    },
    text: {
      primary: "#F2EFE7",
      secondary: "#A9A39A"
    },
    divider: "#34352F",
    action: {
      hover: "rgba(217, 119, 87, 0.1)",
      selected: "rgba(217, 119, 87, 0.18)"
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
          border: "1px solid #34352F",
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
          backgroundColor: "#20211E",
          color: "#F2EFE7"
        }
      }
    },
    MuiOutlinedInput: {
      styleOverrides: {
        root: {
          backgroundColor: "#121311"
        }
      }
    }
  }
});
