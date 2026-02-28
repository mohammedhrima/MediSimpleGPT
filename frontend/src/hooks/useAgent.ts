import { useMutation } from '@tanstack/react-query';
import axios from 'axios';

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
      const response = await axios.post('http://127.0.0.1:8000/connect', data);
      return response.data;
    },
  });
};

export const usePlanTask = () => {
  return useMutation({
    mutationFn: async (data: PlanRequest) => {
      const response = await axios.post('http://127.0.0.1:8000/plan', data);
      return response.data;
    },
  });
};

export const useExecuteActions = () => {
  return useMutation({
    mutationFn: async (data: ExecuteRequest) => {
      const response = await axios.post('http://127.0.0.1:8000/execute', data);
      return response.data;
    },
  });
};

export const useSimplify = () => {
  return useMutation({
    mutationFn: async (data: SimplifyRequest) => {
      const response = await axios.post('http://127.0.0.1:8000/simplify', data);
      return response.data;
    },
  });
};
