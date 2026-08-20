import toast from "react-hot-toast";

export const showToastSuccess = (message: string) => {
  toast.success(message, { 
    style: {
      background: '#4CAF50',
      color: '#ffffff',
    }
  });
}

export const showToastError = (message: string) => {
  toast.error(message, { 
    style: {
      background: '#fee2e2',
    }
  });
}