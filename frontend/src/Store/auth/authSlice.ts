import { createSlice, createAsyncThunk } from "@reduxjs/toolkit";
import { jwtDecode } from "jwt-decode";
import ApiObj from "../../common/ApiObj";
import { fetchRequestPost } from "../../common/NetworkOps";

interface AuthState {
  isLoading: boolean;
  error: string;
  isSuccess: boolean;
  token: string | null;
  user: { sub: number; email: string; role: string } | null;
}

const storedToken = localStorage.getItem("accessToken");

const initialState: AuthState = {
  isLoading: false,
  error: "",
  isSuccess: false,
  token: storedToken,
  user: storedToken ? jwtDecode(storedToken) : null,
};

export const loginUser = createAsyncThunk(
  "auth/loginUser",
  async (credentials: { email: string; password: string }, { rejectWithValue }) => {
    try {
      const response:any = await fetchRequestPost(ApiObj.auth.LOGIN, JSON.stringify(credentials));
      localStorage.setItem("accessToken", response.accessToken);
      console.log(response);
      
      return response;
    } catch (error: any) {
      return rejectWithValue(error.response?.data?.message || "Login failed");
    }
  }
);

export const registerUser = createAsyncThunk(
  "auth/registerUser",
  async (
    credentials: { name: string; email: string; password: string },
    { rejectWithValue }
  ) => {
    try {
      const response: any = await fetchRequestPost(
        ApiObj.auth.REGISTER,
        JSON.stringify(credentials)
      );
      localStorage.setItem("accessToken", response.accessToken);
      return response;
    } catch (error: any) {
      return rejectWithValue(error.response?.data?.message || "Registration failed");
    }
  }
);

const authSlice = createSlice({
  name: "auth",
  initialState,
  reducers: {
    logout: (state) => {
      state.token = null;
      state.user = null;
      localStorage.removeItem("accessToken");
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(loginUser.pending, (state) => {
        state.isLoading = true;
        state.error = "";
        state.isSuccess = false;
      })
      .addCase(loginUser.fulfilled, (state, action: any) => {
        state.token = action.payload.accessToken;
        state.user = jwtDecode(action.payload.accessToken);
        localStorage.setItem("user", JSON.stringify(state.user))
        state.isLoading = false;
        state.isSuccess = true;
      })
      .addCase(loginUser.rejected, (state, action) => {
        state.isLoading = false;
        state.error = action.payload as string;
      })
      .addCase(registerUser.pending, (state) => {
        state.isLoading = true;
        state.error = "";
        state.isSuccess = false;
      })
      .addCase(registerUser.fulfilled, (state, action: any) => {
        state.token = action.payload.accessToken;
        state.user = jwtDecode(action.payload.accessToken);
        localStorage.setItem("user", JSON.stringify(state.user));
        state.isLoading = false;
        state.isSuccess = true;
      })
      .addCase(registerUser.rejected, (state, action) => {
        state.isLoading = false;
        state.error = action.payload as string;
      });
  },
});

export const { logout } = authSlice.actions;
export default authSlice.reducer;