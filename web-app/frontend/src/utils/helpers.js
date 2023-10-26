import axios from "axios";

const API_URL = "https://MY-API-URL-GOES-HERE";

export const postEmail = async (email) => {
  try {
    const res = await axios.post(API_URL, {
      email,
    });
    return { status: res.status, data: res.data };
  } catch (error) {
    return {
      status: error.response.status,
      message: error.response.data.message,
    };
  }
};

export const isValidEmail = (email_address) => {
  // Is email address?
  if (
    !String(email_address)
      .toLowerCase()
      .match(
        /^(([^<>()[\]\\.,;:\s@"]+(\.[^<>()[\]\\.,;:\s@"]+)*)|.(".+"))@((\[[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\])|(([a-zA-Z\-0-9]+\.)+[a-zA-Z]{2,}))$/
      )
  ) {
    return false;
  }
  // Is longer than 35 chars?
  if (email_address.length > 35) {
    return false;
  }
  // Passes validation
  return true;
};
