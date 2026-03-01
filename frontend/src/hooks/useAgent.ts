import { useMutation } from '@tanstack/react-query';
import axios from 'axios';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';

interface ConnectRequest {
  url: string;
}

interface PlanRequest {
  instruction: string;
  dom: string;
}

interface ExecuteRequest {
  actions: string;
  url: string;
}

interface SimplifyRequest {
  url: string;
}

export const useConnect = () => {
  return useMutation({
    mutationFn: async (data: ConnectRequest) => {
      const response = await axios.post(`${API_BASE}/connect`, data);
      return response.data;
    },
  });
};

export const usePlanTask = () => {
  return useMutation({
    mutationFn: async (data: PlanRequest) => {
      const response = await axios.post(`${API_BASE}/plan`, data);
      return response.data;
    },
  });
};

export const useExecuteActions = () => {
  return useMutation({
    mutationFn: async (data: ExecuteRequest) => {
      const response = await axios.post(`${API_BASE}/execute`, data);
      return response.data;
    },
  });
};

export const useSimplify = () => {
  return useMutation({
    mutationFn: async (data: SimplifyRequest) => {
      const response = await axios.post(`${API_BASE}/simplify`, data);
      return response.data;
    },
  });
};
