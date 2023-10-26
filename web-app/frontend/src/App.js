import { useState } from "react";

import { GeistProvider, Grid } from "@geist-ui/core";
import { Button, Text, Card, Spacer, Input, Loading } from "@geist-ui/core";

import { postEmail, isValidEmail } from "./utils/helpers";

const AppComponent = () => {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [validationError, setValidationError] = useState("");
  const [error, setError] = useState("");

  const onEmailChange = (e) => {
    setEmail(e.target.value);
  };

  const onSubmit = async () => {
    setValidationError("");
    if (!isValidEmail(email)) {
      setValidationError("Not a valid email my friend...");
      return;
    }

    setLoading(true);

    const res = await postEmail(email);

    if (res.status !== 200) {
      setError(res.message);
    }

    if (res.status == 200 && res.data) {
      // presigned generated --> redirect user to SageMaker Studio
      window.location.replace(res.data.presigned);
    }
    setEmail("");
  };

  const renderContent = () => {
    if (error) {
      return (
        <Grid.Container justify="center">
          <Text h3 type="error">
            {error}
          </Text>
        </Grid.Container>
      );
    }

    if (loading) {
      return <Loading scale={9 / 3} type="warning" />;
    }

    return (
      <Grid.Container direction="column" alignItems="center">
        <Grid.Container justify="center">
          <Grid xs={15} sm={10} md={7}>
            <Card width="100%" style={{ opacity: "90%" }}>
              <Input
                value={email}
                scale={4 / 3}
                width="95%"
                placeholder="jane.doe@email.com"
                onChange={onEmailChange}
              />
            </Card>
          </Grid>
        </Grid.Container>
        <Spacer h={1} />
        <Grid.Container justify="center">
          <Grid xs={6} sm={3} md={2}>
            <Button
              onClick={onSubmit}
              shadow="100%"
              background="red"
              width="100%"
              type="success-light"
            >
              Go!
            </Button>
          </Grid>
        </Grid.Container>
        {validationError ? (
          <Text h4 type="error">
            {validationError}
          </Text>
        ) : null}
      </Grid.Container>
    );
  };

  return (
    <>
      <Spacer h={20} />
      {renderContent()}
    </>
  );
};

export default () => (
  <GeistProvider>
    <AppComponent />
  </GeistProvider>
);
