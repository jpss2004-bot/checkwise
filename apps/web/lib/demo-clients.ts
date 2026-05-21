/**
 * Hardcoded demo client list (Cliente -> Filiales) for the V1.2 portal demo.
 * All names are fictitious; real client data must never live in source.
 */

export type DemoFilial = {
  name: string;
};

export type DemoClient = {
  name: string;
  filiales: DemoFilial[];
};

export const DEMO_CLIENTS: DemoClient[] = [
  {
    name: "Cliente Piloto CheckWise",
    filiales: [{ name: "Filial Norte" }, { name: "Filial Sur" }],
  },
  {
    name: "Industrias Demo SA de CV",
    filiales: [{ name: "Planta Querétaro" }],
  },
  {
    name: "Servicios Corporativos Demo",
    filiales: [{ name: "Centro" }, { name: "Bajío" }],
  },
];
