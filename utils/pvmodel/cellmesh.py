
from openmesh import *
import writemesh as wr
import ioutils as io
from ioutils import omvec, idtopt, OrderedSet

import numpy as np
from numpy.linalg import norm
import scipy.integrate as integrate

npI = np.identity(3)
def rmmultiply(v, M):
    return np.einsum('n,nm->m', v, M)

import matplotlib.pyplot as plt
from collections import OrderedDict
from scipy.spatial import Delaunay
from read_data import ReadData

from math import pi 
import math as m
import sys

# Samos
from CellList2D import CellList2D

# debugging 


def diagnose(mesh):
    print 'nedges', mesh.n_edges()
    print 'nvertices', mesh.n_vertices()
    print 'nfaces', mesh.n_faces()

from matplotlib import pyplot as plt
def scat(xyz):
    #xyz = np.array([self.meshpt[a] for a in list(self.bulk_edge)])
    plt.scatter(xyz[:,0],xyz[:,1])
    plt.show()


debug = False

# Start of feature code
def in0_1(x):
    return x >= 0 and x <= 1

# define a method for finding all the intersections of bonds with a circle
def bond_intersection(x_c, wl, x_a, x_b):
    # x_c circle centre
    # wl circle radius
    # bond is the vector from particle x_a to particle x_b
    # x_a is the position of particle a, 
    # x_a is going to be the second vertex in the bond pairs

    bond = x_b-x_a
    nca = norm(x_c - x_a)
    ncb = norm(x_c - x_b)

    def line(m):
        return m*bond + x_a

    if nca < wl and ncb < wl:
        return 0, 1, line
    
    # using formula for quadratic ax^2 + bx + c = 0
    a = np.dot(bond, bond)
    b = 2 * np.dot(bond, x_a-x_c)
    c = np.dot(x_c,x_c) + np.dot(x_a,x_a) -2*np.dot(x_c,x_a) - wl**2
    disc = b**2 - 4 * a * c
    if disc <= 0:
        return None 
    else:
        outa, outb = None, None
        sdisc = np.sqrt(disc)
        m_plus = (-b + sdisc)/(2*a)
        m_minus = (-b - sdisc)/(2*a)
        # worry about the exactly which of these should be >,< and >=,<=
        if nca < wl and ncb >= wl:
            # m_plus and m_minus should be one positive one negative in these two cases
            m = m_plus if m_plus > 0 else m_minus
            y= line(m)
            outa, outb = 0, m
            #print 'found a line partly in the smoothing region'
        elif ncb < wl and nca >= wl:
            m_plus = abs(m_plus); m_minus = abs(m_minus)
            m = m_plus if m_plus < m_minus else m_minus
            y = line(m)
            outa, outb = m, 1
            #print 'found a line partly in the smoothing region'
        elif nca >= wl and ncb >= wl:
            outa, outb= m_minus, m_plus
            # The case where a bond line cuts the averaging zone but 
            # the bond itself does not
            if not in0_1(m_minus) or not in0_1(m_plus):
                return None

        if outa is None:
            sys.exit('failed to determine bond intersection')
        return outa, outb, line


# The main object for operating on the cell mesh.
class PVmesh(object):

    def __init__(self, tri):

        self.debug = False

        self.tri = tri
        # the edge mesh (dual mesh)
        self.mesh = None

        # openmesh doesn't store edge lengths?
        self.tri_lvecprop =  self._helengths(self.tri)
        if self.debug:
            print
            print 'trimesh'
            diagnose(self.tri)

        self.boundary = True
        # halfcells = {trimesh.idx() : [mesh vhids] } # should be correctly ordered
        self.halfcells = {}

        self._dual()
        if self.debug:
            print 
            print 'mesh'
            diagnose(self.mesh)

        if self.debug: print 'Calculating edge lengths for mesh'
        self.mesh_lvecprop = self._helengths(self.mesh)

        # Set face normal to e_z
        self.normal = np.array([0,0,1])

        if self.debug: print 'Calculating Area and perimeter'
        self._set_face_properties()

        self.forces = False
        self.is_stress_setup = False
        self.stress = None

        # Use these through out the code in the future instead of idotpt(mesh, v_handle)
        # So 0 corresponds to the triangulation and 1 corresponts to the vertex mesh
        self.meshes = {}
        self.meshes[0] = self.tri
        self.meshes[1] = self.mesh
        # perhaps we should construct python dictionaries for retrieving mesh points and lengths
        self.tript = self._pythonise(self.tri)
        self.tri_bulk = self.get_mesh_bulk(self.tri)
        self.meshpt = self._pythonise(self.mesh)
        self.ptmesh = {}
        self.ptmesh[0] = self.tript
        self.ptmesh[1] = self.meshpt
        
    def _helengths(self, tri):
        # store half edge vectors as half edge property

        lvecprop = HPropHandle()
        tri.add_property(lvecprop, 'lvec')

        for eh in tri.edges():
            heh = tri.halfedge_handle(eh, 0)
            heho = tri.opposite_halfedge_handle(heh)
            vt = tri.to_vertex_handle(heh)
            vf = tri.from_vertex_handle(heh)
            npvt = omvec(tri.point(vt))
            npvf = omvec(tri.point(vf))
            vedge = npvt - npvf
            tri.set_property(lvecprop, heh, vedge)
            tri.set_property(lvecprop, heho, -vedge)
            
        return lvecprop
       
    # How about some tools for dealing with openmesh objects and triangulation
    def iterable_boundary(self, mesh, vh):
        vhidstart = vh.idx()
        def is_boundary_he(mesh, he):
            fh = mesh.face_handle(he)
            return fh.idx() is -1
        start_he = None
        # We need to find the boundary one specifically
        for heh in mesh.voh(vh):
            if is_boundary_he(mesh, heh):
                #print 'found boundary edge for vhid', vh.idx()
                start_he = heh
                break
        assert start_he is not None
        #print 'starting iteration on', start_he.idx()
        def iterable(start_he, mesh):
            he_i = start_he
            while True:
                yield he_i
                he_i = mesh.next_halfedge_handle(he_i)
                if he_i.idx() == start_he.idx():
                    raise StopIteration
        return iterable(start_he, mesh)

    def get_mesh_boundary(self, mesh):
        for vhi in mesh.vertices():
            if mesh.is_boundary(vhi):
                break
        itb = self.iterable_boundary(mesh, vhi)
        bverts = [mesh.to_vertex_handle(heh).idx() for heh in list(itb)]
        return bverts
    
    def get_mesh_bulk(self, mesh):
        bverts = self.get_mesh_boundary(mesh)
        vall= [vhi.idx() for vhi in mesh.vertices()]
        return list(OrderedSet(vall) - OrderedSet(bverts))

    def iterate_boundary_vertex(self, tri, hehp):
        assert tri.is_boundary(hehp)
        facels = []
        while True:
            heho = tri.opposite_halfedge_handle(hehp)
            if tri.is_boundary(heho):
                break
            facels.append(tri.face_handle(heho).idx())
            hehp = tri.prev_halfedge_handle(heho)
        return facels

    
    def _dual(self):
        self.mesh = PolyMesh()

        lambda_prop = FPropHandle()
        self.tri.add_property(lambda_prop, 'lambda')
        self.lambda_prop = lambda_prop

        self.boundary_prop = VPropHandle()
        self.tri.add_property(self.boundary_prop, 'boundary')

        self.boundaries = [] # [[]]
        # add list as well to keep track of which boundary halfedge is outgoing from the vertex
        self.b_nheh = []

        # Trimesh vertice ids and mesh faces ids naturally match up
        ccenters = np.zeros((self.tri.n_faces(),3))
        cradius = np.zeros(self.tri.n_faces())
        for j, fh in enumerate(self.tri.faces()):
            # Calculate circumcentres of mesh
            l_s = np.zeros(3)
            vhs = []
            for i, heh in enumerate(self.tri.fh(fh)):
                lvec =self.tri.property(self.tri_lvecprop, heh)
                l_s[i] = norm(lvec)**2
                vtmp = self.tri.to_vertex_handle(heh)
                vhs.append(vtmp)
                
            # match up vertices and edges 
            vhs = np.roll(vhs, -1, axis=0)
            vi, vj, vk = [omvec(self.tri.point(vh)) for vh in vhs]
            lsi, lsj, lsk = l_s
            lli = lsi*(lsj + lsk - lsi)
            llj = lsj*(lsk + lsi - lsj)
            llk = lsk*(lsi + lsj - lsk)
            # actually want to save lli,llj,llk for later as a face property
            llp = OrderedDict([(vhs[0].idx(),lli), (vhs[1].idx(),llj), (vhs[2].idx(),llk)])
            self.tri.set_property(lambda_prop, fh, llp)

            llnorm = lli + llj + llk
            cc = np.array(lli*vi + llj*vj + llk*vk)/llnorm
            ccenters[j] = cc
            cradius[j] = norm(cc- vi)
        self.cradius = cradius # for visualisation
        # Add cicumcenters to form a new mesh
        tri_prop= VPropHandle()
        self.mesh.add_property(tri_prop, 'tri')
        self.tri_prop = tri_prop
        mverts = np.array(np.zeros(len(ccenters)),dtype='object')
        for j, cc in enumerate(ccenters):
            mverts[j] = self.mesh.add_vertex(PolyMesh.Point(*cc))
            self.mesh.set_property(tri_prop, mverts[j], 0)
        # Add faces
        self.n_tri_internal = 0
        self.n_tri_boundary = 0
        bval = 0
        for vh in self.tri.vertices():
            if self.tri.is_boundary(vh):
                is_new = True not in map(lambda boundary: vh.idx() in boundary, self.boundaries)
                if is_new:
                    bval += 1
                    self.boundaries.append([])
                    self.b_nheh.append([])
                    for heh in self.iterable_boundary(self.tri, vh):
                        #print 'looping along boundary', heh.idx()
                        #print 'adding' , self.tri.from_vertex_handle(heh).idx() 
                        self.boundaries[-1].append( self.tri.from_vertex_handle(heh).idx() )
                        self.b_nheh[-1].append(heh)
                self.tri.set_property(self.boundary_prop, vh, bval)
                self.n_tri_boundary += 1
            else: # Internal vertex
                # construct the face by stepping around the halfedges
                heh = self.tri.halfedge_handle(vh)
                fhs = [ self.tri.face_handle(heh).idx() ]
                start = heh.idx()
                while True:
                    hehp = self.tri.prev_halfedge_handle(heh)
                    heho = self.tri.opposite_halfedge_handle(hehp)
                    if heho.idx() == start:
                        break
                    fh_this = self.tri.face_handle(heho)
                    fhs.append(fh_this.idx())
                    heh = heho

                vhs = list(mverts[fhs])
                mfh = self.mesh.add_face(vhs)
                self.tri.set_property(self.boundary_prop, vh, 0)
                self.n_tri_internal += 1

        # maintain a list of the mesh vertex ids which make up the edge of the internal cells
        self.bulk_edge = set()
        for bv in self.mesh.vertices():
            if self.mesh.is_boundary(bv):
                break
        for heh in self.iterable_boundary(self.mesh, bv):
            nuid= self.mesh.to_vertex_handle(heh).idx()
            #assert self.mesh.is_boundary(self.mesh.vertex_handle(nuid))
            self.bulk_edge.add(nuid)
        self.mesh_bulk = [mvh.idx() for mvh in self.mesh.vertices()] # we didn't add boundary faces yet

        # construct the halfcells object which represents the boundary faces
        # Add boundary triangulation points to the mesh
        self.vh_mf = {}
        self.btv_bmv = {}
        for i, boundary in enumerate(self.boundaries):
            for j, vhid in enumerate(boundary):
                vh = self.tri.vertex_handle(vhid)
                hehn = self.b_nheh[i][j]
                hehp = self.tri.prev_halfedge_handle(hehn)
                # write custom function for iterating around a vertex starting from hehp
                halfcell= self.iterate_boundary_vertex(self.tri, hehp)
                self.halfcells[vhid] = halfcell

                tript = omvec(self.tri.point(self.tri.vertex_handle(vhid)))
                mvh = self.mesh.add_vertex(PolyMesh.Point(*tript))
                self.mesh.set_property(tri_prop, mvh, 1)

                hcf = list(mverts[halfcell])
                hcf.append(mvh)
                mfh = self.mesh.add_face(hcf)

                self.btv_bmv[vhid] = mvh.idx()
                self.vh_mf[vhid] = mfh.idx()

        self.true_mesh_boundary = self.get_mesh_boundary(self.mesh)

    def _set_face_properties(self):
        # organise the properties we will use
        mesh = self.mesh
        tri = self.tri
        areaprop = VPropHandle()
        self.tri.add_property(areaprop, 'area')
        primprop = VPropHandle()
        self.tri.add_property(primprop, 'prim')
        self.btheta_prop = VPropHandle()
        self.tri.add_property(self.btheta_prop, 'angular defecit')

        for vh in tri.vertices():
            vhid = vh.idx()
            area = 0.
            prim = 0.
            ag = 1. # Angular defecit. Set it to one for internal vertices
            boundary = tri.is_boundary(vh)
            if not boundary:
                fh = mesh.face_handle(vh.idx())
                for heh in mesh.fh(fh):
                    # mirror this with the boundary calculation and forget about lvecprop
                    rmu = omvec(mesh.point(mesh.from_vertex_handle(heh)))
                    rmup = omvec(mesh.point(mesh.to_vertex_handle(heh)))
                    area += np.dot(np.cross(rmu, rmup), self.normal)
                    ap=  np.dot(np.cross(rmu, rmup), self.normal)
                    lvec = mesh.property(self.mesh_lvecprop, heh)
                    l = norm(lvec)
                    prim += l
                area = area/2
            else:
                # calculate area for boundary vertices
                hcell = self.halfcells[vhid]
                hcellpts = map(lambda x: omvec(self.mesh.point(mesh.vertex_handle(x))), hcell) 
                r_i = omvec(self.tri.point(vh))
                hcellpts.append(r_i)
                n = len(hcellpts)
                for i, hpt in enumerate(hcellpts):
                    ip = (i+1) % n
                    area += np.dot(np.cross(hpt, hcellpts[ip]), self.normal)
                    l = norm(hpt-hcellpts[ip])
                    prim += l
                area = area/2

                # Calculate angular defecit for boundary vertices
                # Could store real angular defecit here or the updated target areas
                # Go with storing angular defecit
                r_p = omvec(tri.point(vh))
                hc = self.halfcells[vh.idx()]
                r_mu_1, r_mu_n = idtopt(mesh, hc[0]), idtopt(mesh, hc[-1])
                r_mu_1_p = r_mu_1 - r_p
                r_mu_n_p = r_mu_n - r_p
                dtheta = np.arccos( np.dot(r_mu_1_p, r_mu_n_p) / (norm(r_mu_1_p) * norm(r_mu_n_p)) )
                sg = np.dot( np.cross(r_mu_1_p , r_mu_n_p), self.normal) >= 0
                ag = dtheta if sg else 2*pi - dtheta
                ag /= 2*pi

            self.tri.set_property(self.btheta_prop, vh, ag)
            #print 'setting angular defecit of', ag
            #print 'setting area of', area
            #print 'setting perimeter of', prim
            self.tri.set_property(areaprop, vh, area)
            self.tri.set_property(primprop, vh, prim)

        self.areaprop = areaprop
        self.primprop = primprop

    def _construct_cl_dict(self, L):
        # create a dictionary for the L property 
        # this code sets values for every edge however boundary->boundary edges do not correspond to a cell edge
        mesh =self.mesh
        cl_dict = {}
        for eh in self.mesh.edges():
            heh = self.mesh.halfedge_handle(eh, 0)
            vhi = self.mesh.to_vertex_handle(heh)
            vhj = self.mesh.from_vertex_handle(heh)
            vhidx = vhi.idx(); vhjdx = vhj.idx()
            cl_dict[(vhidx, vhjdx)] = L 
            cl_dict[(vhjdx, vhidx)] = L 
        return cl_dict

    def set_constants(self, K, Gamma, cl_dict):
        # Constants for Area and Perimeter should be in .dat file? Let them be set manually.
        kprop = VPropHandle()
        self.tri.add_property(kprop, 'K')
        gammaprop = VPropHandle()
        self.tri.add_property(gammaprop, 'Gamma')
        # Need to start thinking in terms of edges for the contact length property
        clprop = EPropHandle()
        self.mesh.add_property(clprop, 'Contact Length')

        for i, (ki, gi) in enumerate(zip(K, Gamma)):
            vh = self.tri.vertex_handle(i)
            self.tri.set_property(kprop, vh, ki)
            self.tri.set_property(gammaprop, vh, gi)
        # Edges are defined between faces so need to give a dictionary of constants for generality
        for eh in self.mesh.edges():
            heh = self.mesh.halfedge_handle(eh, 0)
            vhi =  self.mesh.to_vertex_handle(heh)
            vhj = self.mesh.from_vertex_handle(heh)
            vhidx = vhi.idx(); vhjdx = vhj.idx()
            self.mesh.set_property(clprop, eh, cl_dict[(vhidx, vhjdx)])

        self.kprop = kprop
        self.gammaprop = gammaprop
        self.clprop = clprop


    # Iterate through the mesh vertices for any cell (even boundary)
    def loop(self, trivh, halfedges=False):
        tri = self.tri; mesh = self.mesh
        trivhid = trivh.idx()
        boundary = tri.is_boundary(trivh)
        vhs = []
        hehs = []
        if not boundary:
            fh = mesh.face_handle(trivhid)
        else:
            fh = mesh.face_handle(self.vh_mf[trivhid])

        for mheh in mesh.fh(fh):
            vh = mesh.from_vertex_handle(mheh)
            vhs.append(vh.idx())
            hehs.append(mheh.idx())
        if halfedges:
            return vhs, hehs
        else:
            return vhs


    def calculate_energy(self):
        # And attach values as a property to the faces of the mesh (inner vertices of triangulation)
        mesh = self.mesh
        tri = self.tri

        # might as well store the energy associated with each face
        enprop = VPropHandle()
        tri.add_property(enprop, 'energy')

        # Iterate over faces
        tenergy = 0
        for vh in tri.vertices():
            prefarea = tri.property( self.prefareaprop, vh )
            ag = tri.property( self.btheta_prop,vh)
            area = self.tri.property(self.areaprop, vh)
            k = self.tri.property(self.kprop, vh)

            farea = k/2 * (area - ag*prefarea)**2
            gamma = tri.property(self.gammaprop, vh)
            perim = tri.property(self.primprop, vh)
            fprim = gamma/2 * perim**2


            #do we need the energy of each cell independently?
            e_cl = 0.
            # Add internal idx to vh_mf to avoid this check
            m_face_id = self.vh_mf[vh.idx()] if tri.is_boundary(vh) else vh.idx()  
            m_face = mesh.face_handle(m_face_id) 
            for heh in mesh.fh(m_face):
                #print m_face.idx(), 
                #print mesh.is_boundary(m_face)
                li = norm(mesh.property(self.mesh_lvecprop, heh))
                eh= mesh.edge_handle(heh)
                cl= mesh.property(self.clprop, eh)
                # IMPORTANT, we made a choice in handling the extra boundary edges here, don't forget!
                e_cl += 1/2. * cl * li 

            #print e_cl
            fen = farea + fprim + e_cl
            tri.set_property(enprop, vh, fen)
            tenergy += fen
        print 'total energy of mesh', 
        print tenergy

        self.enprop = enprop

    def calculate_forces(self):
        # Convenience
        mesh = self.mesh
        tri = self.tri
        lvecprop = self.tri_lvecprop

        # Maybe start by calculating d[lambda_i]/d[r_p] for {i,j,k} on each face p
        # drmudrp[mesh_vhid, mesh_fhid, :]
        drmudrp = {}
        for tri_fh in tri.faces():
            vh = mesh.vertex_handle(tri_fh.idx())
            #dlamqdrp {tri_vh.idx() : np(3,3) }
            dlamqdrp = {}
            drmudrp[vh.idx()] = {}
            # Get the corresponding face
            lq = np.zeros((3,3))
            lqs = np.zeros(3)
            r_q = np.zeros((3,3))
            r_qvh= []
            for i, hehq in enumerate(self.tri.fh(tri_fh)):
                lq[i] = tri.property(lvecprop, hehq)
                lqs[i] = norm(lq[i])**2
                vhi = tri.to_vertex_handle(hehq)
                r_qvh.append(vhi.idx())
            
            r_qvh = np.roll(r_qvh, -1, axis=0)
            r_q = np.array([omvec(self.tri.point(self.tri.vertex_handle(trivh))) for trivh in r_qvh])
            rjk, rki, rij = -lq
            lis, ljs, lks =  lqs
            # Stepping towards calculating the jacobian
            # we do this for each cell around the vertices
            i = r_qvh[0]
            dlamqdrp[i] = np.zeros((3,3))
            dlamqdrp[i][0,:] = 2*lis*(-rki + rij)
            dlamqdrp[i][1,:] = -2*(lis + lks - 2*ljs)*rki + 2*ljs*rij
            dlamqdrp[i][2,:] = 2*(lis + ljs -2*lks)*rij - 2*lks*rki

            j = r_qvh[1]
            dlamqdrp[j] = np.zeros((3,3))
            dlamqdrp[j][0,:] = 2*(ljs + lks - 2*lis)*rjk - 2*lis*rij
            dlamqdrp[j][1,:] = 2*ljs*(rjk-rij)
            dlamqdrp[j][2,:] = -2*(lis + ljs -2*lks)*rij + 2*lks*rjk

            k = r_qvh[2]
            dlamqdrp[k] = np.zeros((3,3))
            dlamqdrp[k][0,:] = -2*(ljs + lks - 2*lis)*rjk + 2*lis*rki
            dlamqdrp[k][1,:] = 2*(lis + lks -2*ljs)*rki - 2*ljs*rjk
            dlamqdrp[k][2,:] = 2*lks*(-rjk + rki)

            dLambdadrp = {}
            for key, arr in dlamqdrp.items():
                dLambdadrp[key] = np.sum(arr, axis=0)
            lambdaq = tri.property(self.lambda_prop, tri_fh)

            gamma = sum(lambdaq.values())
            # The jacobian for each mesh vertex and adjacent face
            for p in dlamqdrp.keys():
                t1 = gamma * np.einsum('qm,qn->mn', r_q, dlamqdrp[p])
                t2 = gamma * lambdaq[p] * np.identity(3)
                lqrq = np.einsum('q,qn->n', lambdaq.values(), r_q)
                t3 = np.outer(lqrq, dLambdadrp[p])
                drmudrp[vh.idx()][p] = (1/gamma**2) * (t1 + t2 - t3)

        # For calculating derivative of area for boundary cells 
        for boundary in self.boundaries:
            print boundary
            for j, vhid in enumerate(boundary):
                mvhid = self.btv_bmv[vhid]
                drmudrp[mvhid] = {}

                #print 'extra drmudrp', mvhid, vhid
                #if mvhid == 2122 or vhid == 1015:
                    #print 'extra drmudrp', mvhid, vhid
                drmudrp[mvhid][vhid] = np.identity(3)

        #alias
        loop = self.loop

        # Nearest Neighbour faces
        # ( by vertex )

        def nnfaces(trivh):
            fhs = []
            for heh in tri.voh(trivh):
                vh = tri.to_vertex_handle(heh)
                fhs.append(vh)
            return fhs

        # Calculate loops 
        # loops {fid:set(vhids)}
        loops = {}
        for vh in tri.vertices():
            loops[vh.idx()] = loop(vh)
        #io.stddict(loops)
        # Calculate loop interesctions
        # {vhi:{vhj:set(v1_idx,v2_idx..)}}
        # It's natural to use sets and the intersect() method for dealing with loops
        interloops = {}
        for vhi in tri.vertices():
            vhidx = vhi.idx()
            interloops[vhidx] = {}
            for vhj in nnfaces(vhi):
                vhjdx = vhj.idx()
                intset = set(loops[vhidx]).intersection(set(loops[vhjdx]))
                interloops[vhidx][vhjdx] = intset


        # dAdrmu[fhid][vhid]  
        # this should work for boundary cells as well
        dAdrmu = {}
        dPdrmu = {}
        dLdrmu =  {}
        for trivh in tri.vertices():
            trivhid = trivh.idx()
            dAdrmu[trivhid] = {}
            dPdrmu[trivhid] = {}
            dLdrmu[trivhid] = {}

            # These are the vertices of the loop
            # how about the halfedges
            lp, hp = loop(trivh, halfedges=True)
            nl = len(lp)
            for i, vhid in enumerate(lp):
                vh = mesh.vertex_handle(vhid)

                # Caluculate area and perimeter derivatives on the vertices 
                # need next and previous vertices
                ni = (i+1) % nl
                npr = (i-1) % nl
                vhplus = mesh.vertex_handle(lp[ni])
                vhminus = mesh.vertex_handle(lp[npr])

                vplus, vminus = omvec(mesh.point(vhplus)), omvec(mesh.point(vhminus))
                dAdrmu[trivhid][vhid] = 1/2. * ( np.cross(vplus, self.normal) 
                        - np.cross(vminus, self.normal) )
                #dPdrmu
                # get lengths
                vhpt = omvec(mesh.point(vh))
                lvm = vhpt - vminus
                lvp = vplus - vhpt
                dPdrmu[trivhid][vhid] = lvm/norm(lvm) - lvp/norm(lvp)

                #dLdrmu
                # for this mesh vertex what are the surrounding points in cell (mesh face) trivh 

                mhehid = hp[i] # outgoing halfedge
                mheh = mesh.halfedge_handle(mhehid)
                mhehm = mesh.prev_halfedge_handle(mheh)
                lv = mesh.property(self.mesh_lvecprop, mheh)
                lmv = mesh.property(self.mesh_lvecprop, mhehm)
                lv = lv/norm(lv); lmv = lmv/norm(lmv)

                cl = mesh.property(self.clprop, mesh.edge_handle(mheh))
                clm = mesh.property(self.clprop, mesh.edge_handle(mhehm))
                # 1/2. factor here becuase each edge is iterated over twice in summing the forces
                dLdrmu[trivhid][vhid] = 1/2. * ( clm * lmv - cl * lv )

        fprop = VPropHandle()
        tri.add_property(fprop, 'force')
        self.fprop = fprop

        # The duplicated code involved in determining the angle defecit derivative
        #  for the primary and adjacent faces
        def setup_rmu(vhid):
            hc = self.halfcells[vhid]
            mu1, mun = hc[0], hc[-1] # mesh vertices
            rmu1, rmun = idtopt(self.mesh, hc[0]), idtopt(mesh, hc[-1])
            ri = idtopt(self.tri, vhid)
            r1, rn = rmu1 - ri, rmun -ri
            nr1, nrn = norm(r1), norm(rn)
            agarg = np.dot(r1, rn) / (nr1 *nrn)
            sgn = -1 if np.dot( np.cross(r1 , rn), self.normal) >= 0. else 1
            pre_fac = sgn *  1/(2*pi) * 1/np.sqrt(1-agarg**2) 
            return mu1, mun, rmu1, rmun, nr1, nrn, r1, rn, pre_fac

        # Angle defecit derivative
        # dzetadr[boundary vertex][i, j, k vertex]
        dzetadr = {}
        for bd in self.boundaries:
            nbd = len(bd)
            for i, vhid in enumerate(bd):
                dzetadr[vhid] = {}
                vh = tri.vertex_handle(vhid)
                #ag = self.tri.property(self.btheta_prop, vh)
                jm = (i-1) % nbd
                jp = (i+1) % nbd

                vhmid = bd[jm]
                vhpid = bd[jp]
                # Calculate dzetadr[i][i], setup
                mu1, mun, rmu1, rmun, nr1, nrn, r1, rn, pre_fac = setup_rmu(vhid)
                # derivative 
                d1 =1/( nr1 * nrn)
                d2 = np.dot(r1, rn) * d1**2
                v1a = rmmultiply(rn, drmudrp[mu1][vhid] -npI) 
                v1b = rmmultiply(r1, drmudrp[mun][vhid] -npI)
                v2a = nr1 * rmmultiply( (rn/nrn), drmudrp[mun][vhid] - npI) 
                v2b = nrn*  rmmultiply( (r1/nr1), drmudrp[mu1][vhid] - npI)
                #deriv_X = d1 * v1 - d2 * ( v2a + v2b )
                #deriv_ag = pre_fac * deriv_X
                #dzetadr[vhid][vhid] = deriv_ag

                dzetadr[vhid][vhid] = {}
                dzetadr[vhid][vhid][mu1] = pre_fac * (d1 * v1a - d2 * v2a)
                dzetadr[vhid][vhid][mun] = pre_fac * (d1 * v1b - d2 * v2b)

                # i, j where j is over nearest neighbours
                lp = nnfaces(vh)
                nl = len(lp)
                for j, nnvh in enumerate(lp):
                    nnvhid = nnvh.idx()
                    dzetadr[vhid][nnvhid] = {}
                    cell_verts = set([mu1, mun]).intersection(interloops[vhid][nnvhid])
                    if bool(cell_verts) is False:
                        # This is the case where an adjacent cell shares no boundary vertices
                        continue
                    deriv_X = np.zeros(3)
                    for mu in cell_verts:
                        assert (mu == mu1) or (mu == mun)
                        rmu, rother = [r1, rn] if mu == mu1 else [rn, r1]
                        nrmu = norm(rmu); nrother = norm(rother)
                        dzX = ( rmmultiply( rother/(nr1 * nrn), drmudrp[mu][nnvhid])
                                - np.dot(r1,rn)/(nr1 * nrn)**2 * nrother
                                * rmmultiply( rmu/nrmu, drmudrp[mu][nnvhid] ) )
                        deriv_X = dzX

                        dzetadr[vhid][nnvhid][mu] = pre_fac * deriv_X
                    #dzetadr[vhid][nnvhid] = pre_fac * deriv_X
                    
        # It remains to do some complicated math over loops of nearest neighbours, etc..
        # We also want to calculate stress now
        # {vhid: s_arr}
        a_stress = OrderedDict()
        p_stress = OrderedDict()
        l_stress = OrderedDict()
        stress = OrderedDict()
        
        for trivh in tri.vertices():
            fh = self.mesh.face_handle(trivh.idx())
            trivhid = trivh.idx()
            fhidx = fh.idx()
            # fhidx = trimesh vertices id
            kp = tri.property(self.kprop, trivh)
            gammap = tri.property(self.gammaprop, trivh)
            area = tri.property(self.areaprop, trivh)
            prim = tri.property(self.primprop, trivh)
            prefarea = self.tri.property(self.prefareaprop, trivh)
            ag = self.tri.property(self.btheta_prop, trivh)

            trivhpt = omvec(self.tri.point(trivh))
            stress[trivhid] = np.zeros((3,3))
            a_stress[trivhid] = np.zeros((3,3))
            p_stress[trivhid] = np.zeros((3,3))
            l_stress[trivhid] = np.zeros((3,3))
            boundary = tri.is_boundary(trivh)

            # Immediate contribution
            farea_fac = -(kp) * (area - ag *prefarea)  
            fprim_fac = -(gammap) * prim
            asum = np.zeros(3)
            psum = np.zeros(3)
            lsum = np.zeros(3)

            # dAdrp and dPdrp
            for mu in loops[trivhid]:
                r_mu_vh = idtopt(mesh, mu) - trivhpt # precalculate these
                if trivhid == 1015: print trivhid, mu, fhidx

                dAdrmu[trivhid][mu]
                drmudrp[mu][trivhid]
                ac = rmmultiply(dAdrmu[trivhid][mu], drmudrp[mu][trivhid])
                pc = rmmultiply(dPdrmu[trivhid][mu], drmudrp[mu][trivhid])
                lc = rmmultiply(dLdrmu[trivhid][mu], drmudrp[mu][trivhid])
                if boundary: # angle defecit contribution
                    if mu in dzetadr[trivhid][trivhid]:
                        zetat = dzetadr[trivhid][trivhid][mu] * prefarea
                        ac -= zetat

                a_stress[trivhid] += farea_fac * np.outer(ac, r_mu_vh)
                p_stress[trivhid] += fprim_fac * np.outer(pc, r_mu_vh)
                l_stress[trivhid] += -1 * np.outer(lc, r_mu_vh)
                asum += ac
                psum += pc
                lsum += lc

            farea = farea_fac * asum
            fprim = fprim_fac * psum
            # no extra factor
            flc = -1 * lsum

            # And the nearest neighbours contribution
            # Some duplicated code
            area_nnsum = np.zeros(3)
            prim_nnsum = np.zeros(3)
            lc_nnsum = np.zeros(3)
            for vhnn, vidset in interloops[trivhid].items():
                nnvh = tri.vertex_handle(vhnn)

                kp = tri.property(self.kprop, nnvh)
                gammap = tri.property(self.gammaprop, nnvh)
                area = tri.property(self.areaprop, nnvh)
                prim = tri.property(self.primprop, nnvh)
                prefarea = tri.property(self.prefareaprop, nnvh)
                ag = self.tri.property(self.btheta_prop, nnvh)

                farea_fac = -(kp) * (area - ag * prefarea)  
                fprim_fac = -(gammap) * prim
                asum = np.zeros(3)
                psum = np.zeros(3)
                lsum = np.zeros(3)

                nnboundary = tri.is_boundary(nnvh)
                for mu in vidset:
                    r_mu_vh = idtopt(mesh, mu) - trivhpt
                    ac = np.einsum('n,nm->m', dAdrmu[vhnn][mu], drmudrp[mu][trivhid])
                    pc = np.einsum('n,nm->m', dPdrmu[vhnn][mu], drmudrp[mu][trivhid])
                    lc = np.einsum('n,nm->m', dLdrmu[vhnn][mu], drmudrp[mu][trivhid])
                    if nnboundary:
                        vht = mu in dzetadr[vhnn][trivhid]
                        if vht:
                            # the angle defecit contribution
                            zetat = dzetadr[vhnn][trivhid][mu] * prefarea
                            ac -= zetat
                    asum += ac
                    psum += pc
                    lsum += lc
                    a_stress[trivhid] += farea_fac  * np.outer(ac, r_mu_vh)
                    p_stress[trivhid] += fprim_fac * np.outer(pc, r_mu_vh)
                    l_stress[trivhid] += -1 * np.outer(lc, r_mu_vh)

                area_nnsum += farea_fac * asum
                prim_nnsum += fprim_fac * psum
                lc_nnsum += -1 * lsum

            imforce = farea + fprim + flc
            nnforce = area_nnsum + prim_nnsum + lc_nnsum
            totalforce = imforce + nnforce
            tri.set_property(fprop, trivh, totalforce)

            stress[trivhid] = a_stress[trivhid] + p_stress[trivhid]

        self.n_stress = stress
        self.forces = True

    def _pythonise(self, mesh):
        meshpt = OrderedDict()
        for vh in mesh.vertices():
            meshpt[vh.idx()] = omvec(mesh.point(vh))
        return meshpt

    def _construct_bonds(self):
        tript = self.tript; meshpt = self.meshpt
        bonds = {}
        self.bonds = bonds
        # remove boundary bonds from the list here
        #for vhi in self.tri.vertices():
        for i in self.tri_bulk:
            vhi = self.tri.vertex_handle(i)
            for vhnu in self.loop(vhi):
                nu = vhnu
                r = tript[i] - meshpt[nu]
                bonds[frozenset([(0,i),(1,nu)])] = r
        for eh in self.mesh.edges():
            heh = self.mesh.halfedge_handle(eh, 0)
            nu = self.mesh.to_vertex_handle(heh).idx()
            mu = self.mesh.from_vertex_handle(heh).idx()
            # removing the rest of the boundary cell bonds
            if nu in self.true_mesh_boundary and mu in self.true_mesh_boundary: 
                continue
            r_nu_mu = meshpt[nu] - meshpt[mu]
            bonds[frozenset([(1,nu),(1,mu)])] = r_nu_mu



    def _calculate_dEdlength(self):
        # because we split the bonds into separate dictionaries
        # we need to do the same here.
        tri = self.tri; mesh = self.mesh
        tript = self.tript; meshpt = self.meshpt
        bonds = self.bonds

        # in order to manage cell areas lets create a little mesh for each cell
        polygons = TriMesh()
        # map the new single cell mesh vertices back onto our meshes
        # we have to keep track of which mesh our ids belong to 
        # {new_mesh_id: ('t', old_mesh_id)
        pullback = {} 
        # {('t', old_mesh_id): new_mesh_id}
        pushforward = {}
        for mu in self.mesh_bulk:
            mupt = meshpt[mu]
            mv = polygons.add_vertex(TriMesh.Point(*mupt))
            pushforward[(1, mu)] = mv.idx()
            pullback[mv.idx()] = (1, mu)
        for p in self.tri_bulk:
            vhi = tri.vertex_handle(p)
            ipt = tript[p]
            pts = []
            # we assume this loop orders the points counter-clockwise as they should be
            loop = self.loop(vhi)
            lnupts = len(loop)
            mv = polygons.add_vertex(TriMesh.Point(*ipt))
            centerid = mv.idx()
            pushforward[(0, p)] = centerid
            pullback[centerid] = (0, p)
            nuvertids = [pushforward[(1,nu)] for nu in loop]
            #pullback[mv.idx()] = (0, p)
            #for i, (vhnu, v) in enumerate(zip(loop, nupts)):
                #mv = polygon.add_vertex(TriMesh.Point(*v))
                #mverts[i+1] = mv
                #pullback[mv.idx()] = (1, vhnu)
            simplices = np.zeros((lnupts, 3),dtype=int)
            for i, (nu, mu) in enumerate(zip(nuvertids, np.roll(nuvertids, -1, axis=0))):
                simplices[i,0] = centerid
                simplices[i,1] = nu
                simplices[i,2] = mu
            for f in simplices:
                polygons.add_face([polygons.vertex_handle(vid) for vid in f])
            # semi perimeters and lengths should be precalculated

        polygon_l = {}
        for eh in polygons.edges():
            heh = polygons.halfedge_handle(eh, 0)
            av= polygons.from_vertex_handle(heh)
            bv= polygons.to_vertex_handle(heh)
            a = norm(omvec(polygons.point(av) -polygons.point(bv)))
            polygon_l[frozenset([av.idx(),bv.idx()])] = a


        def get_star_hedges(polgons, vhi):
            hehids = []
            for fh in polygons.vf(vhi):
                for heh in polygons.fh(fh):
                    hehids.append(heh.idx())
            return set(hehids)

        dEdbond = {}
        for i in self.tri_bulk:
            vhi= tri.vertex_handle(i)

            kp = tri.property(self.kprop, vhi)
            gammap = tri.property(self.gammaprop, vhi)
            area = tri.property(self.areaprop, vhi)
            prim = tri.property(self.primprop, vhi)
            prefarea = self.tri.property(self.prefareaprop, vhi)
            
            pre = kp*(area - prefarea)
            # pick out triangles
            nc = 0.

            pvhi = polygons.vertex_handle(pushforward[(0, i)])
            for hehid in get_star_hedges(polygons, pvhi):
                heh = polygons.halfedge_handle(hehid)
                av = polygons.from_vertex_handle(heh)
                bv = polygons.to_vertex_handle(heh)
                avid = av.idx(); bvid = bv.idx()
                avidk = pullback[avid]; bvidk = pullback[bvid]
                bondk = frozenset([avidk, bvidk])

                # add contributions from two faces if they exist
                f= polygons.face_handle(heh)

                fid = f.idx()
                vhs = [fv.idx() for fv in polygons.fv(f)]

                bond_pairs = map(frozenset, zip(vhs, np.roll(vhs, -1)))
                lls = [polygon_l[bp] for bp in bond_pairs]
                # derivative with respect to the length dl
                dl = bond_pairs.index(frozenset([avid,bvid]))
                a, b, c = np.roll(lls, -dl)
                s = (a + b + c)/2
                #assert a == norm(omvec(polygon.point(av) - polygon.point(bv)))
                sa = s - a; sb = s - b; sc = s - c
                # should precalculate, todo
                cald = s*sa*sb*sc
                assert cald >= 0
                triA = np.sqrt(cald)
                preA = 1/(2. * triA)

                dDdbond = 1/2. *  ( -a*sb*sc + s*sa*sc + s*sa*sb )
                dAdbond = preA * dDdbond

                if bondk not in dEdbond:
                    dEdbond[bondk] = 0.
                dEdbond[bondk] += pre * dAdbond
        self.dEdbond = dEdbond

    def _set_wl(self, omega):
        wl = omega.wl
        block = np.array(self.tript.values() + self.meshpt.values())
        Lx, Ly, mzero = np.amax(np.abs(block),axis=0)
        assert mzero == 0.
        cut = np.sqrt((self.lmax**2)/4. + wl**2) + 0.1
        print 'setting cut off distance to ', cut
        cl = CellList2D([2*Lx+1, 2*Ly+1], cut)
        # construct a cell list for all the vertices and centres
        # can construct separate cell lists for both
        # Then when it comes to checking intersections only do it for bonds which have both
        # ends within the neighbouring cells.
        for i, ipt in self.tript.items():
            cl.add_particle(ipt[:2], (0, i))
        for nu, nupt in self.meshpt.items():
            cl.add_particle(nupt[:2], (1, nu))
        self.cl = cl

    def _stress_setup(self, omega=None):
        self._construct_bonds()
        self._calculate_dEdlength()
        self.lmax = max(map(norm, self.bonds.values()))
        tript = self.tript; meshpt = self.meshpt
        if omega:
            self._set_wl(omega)
            self.is_stress_setup = True

    def calculate_stress(self, x_c, omega):
        # wl is the smoothing length
        # x_c the point about which we calculate stress

        mesh = self.mesh; tri = self.tri
        tript, meshpt= self.tript, self.meshpt
        bonds = self.bonds 
        lmax = self.lmax
        is_near = self.cl.proximity_def(x_c)

        # Need to cut out all the bonds which are too far away to be worth checking. Efficiently.
        stress = np.zeros((3,3))
        dEdbond = self.dEdbond
        nc = 0

        for bondk in bonds.keys(): 
            # The 't' type of bond identifies ibonds and nubonds
            bka, bkb = bondk
            ta, a = bka; tb, b = bkb
            pta = self.ptmesh[ta][a]
            ptb = self.ptmesh[tb][b]
            
            if not (is_near(pta) or is_near(ptb)):
                continue
#            neighbours= self.cl.get_neighbours(x_c)
            #if bka not in neighbours and bkb not in neighbours:
                #continue # bond is too far away to bother checking
            bondv = pta-ptb
            inter = bond_intersection(x_c, omega.wl, pta, ptb)
            if inter is None:
                continue # couldn't find an intersection
            m_minus, m_plus, line = inter

            def omegaline(m):
                return omega( norm(line(m) - x_c) )

            # Non-zero stress contribution
            # do this check earlier todo
            if ta == 1 and tb == 1 and (a in self.bulk_edge) and (b in self.bulk_edge):
                #print 'excluding stress with bond', a,b 
                #print 'at positions', meshpt[a], meshpt[b]
                stress = None
                break 
            bondv_hat = bondv/norm(bondv)
            omega_int, err = integrate.quad(omegaline, m_minus, m_plus)
            #print 'm_cuts', m_minus, m_plus
            #print 'integration', line(m_minus), line(m_plus), omega_int
            #io.plotrange(omegaline, m_minus, m_plus)
            stress += -dEdbond[bondk] * omega_int * np.outer(bondv_hat, bondv)
            #print -dEdbond[bondk] 
            #print
            nc += 1
    
        if stress is None: return stress
        #print 'added stress with %d contributions' % nc
        #stress *= -1./(pi * wl**2)
        return stress

    def calculate_vflow(self, x_c, omega):
        vvals = self.vvals
        vflow = 0.
        for k in self.cl.get_neighbours(x_c):
            ti, i = k
            if ti == 0:
                ipt = self.tript[i]
            else: 
                continue
            nix = norm(ipt - x_c)
            vflow += omega(nix) * vvals[i]
        return vflow

    def calculate_kinetic_stress(self, x_c, omega):

        mesh = self.mesh; tri = self.tri
        tript, meshpt= self.tript, self.meshpt

        stressk = np.zeros((3,3))
        vvals = self.vvals
        # include boundaries for the moment just don't calculate stress for them
        for k in self.cl.get_neighbours(x_c):
            ti, i = k
            if ti == 0:
                ipt = self.tript[i]
            else:
                continue
            vflow = self.calculate_vflow(x_c, omega)
            vrel = vvals[i] - vflow
            # mass is 1
            stressk -= np.outer(vrel, vrel) * omega(norm(x_c -ipt))
        return stressk

    def stress_on_centres(self, omega, clist=None, kinetic=True):
        stress = OrderedDict() # wipe out previous stress in force calculation if it exists
        stressk = OrderedDict()
        pressure = OrderedDict()
        #excl = []
        if clist is None: clist = self.tri_bulk
        for i in clist:
            vhi = self.tri.vertex_handle(i)
            if i % 100 == 0:
                print 'Made it to vertex', i
            ipt = self.tript[i]
            ss =  self.calculate_stress(ipt, omega)
            if kinetic:
                ssk = self.calculate_kinetic_stress(ipt, omega)
                stressk[i] = ssk
            #if ss is None:
                #print 'excluded stress for cell', i
                #excl.append(ipt)

            stress[i] = ss
            # pressure should have a factor here. 1/3 ? 
            pressure[i] = None if ss is None else np.trace(ss)
            #print stressk[i][:2,:2]
           
            #print stress[i][:2,:2]  if stress[i] != None else None
            #print 
        print 'Made it to vertex', i
        #scat(np.array(excl))
        self.clist = clist
        self.stress= stress
        self.pressure = pressure

    # Now we have self.stress and self.pressure the next step is to 
    #  reduce to averaged quantities
    def radial(self, nstat=100.):
        # first find the centre of mass
        #triptarr = np.array(self.tript.values())
        #triptarr = self.pressure.keys()
        triptarr = np.array([self.tript[i] for i in self.clist])
        ltript = len(triptarr)
        rcm = np.sum(triptarr, axis=0)/ltript
        print 'the centre of mass for the tissue', rcm
        #now bin the points according to their distance from the centre
        def distrcm(rval):
            return norm(rval-rcm)
        rcmd = map(distrcm, triptarr)
        mrc = np.max(rcmd)
        nbins = m.ceil(ltript/nstat)
        rspace = np.linspace(0, mrc, nbins+1, endpoint=True)
        # the bin index of each point based on distance from rcmb
        npd = np.digitize(rcmd, rspace, right=True)-1
        # It remains to average the contents of each bin
        assert nbins == len(rspace)-1
        ravg = np.zeros(nbins)
        hcount = np.zeros(nbins)
        for i, bn in zip(self.clist, npd):
            prs = self.pressure[i]
            if prs is None: continue
            ravg[bn] += prs
            hcount[bn] += 1
        radial_pressure = np.true_divide(ravg, hcount)
        self.rspace = rspace
        self.radial_pressure = radial_pressure
        #plt.plot(rspace[:-1], radial_pressure)
        #plt.show()

    ''' This is really the constructor '''
    @classmethod
    def datbuild(cls, rdat, simplices=None):
        keys = rdat.keys
        x = np.array(rdat.data[keys['x']])
        y = np.array(rdat.data[keys['y']])
        z = np.array(rdat.data[keys['z']])
        vx = np.array(rdat.data[keys['vx']])
        vy = np.array(rdat.data[keys['vy']])
        vz = np.array(rdat.data[keys['vz']])

        area = np.array(rdat.data[keys['area']])
        #rvals = np.column_stack([x, y, z])
        rvals = np.column_stack([x, y, z])
        vvals = np.column_stack([vx, vy, vz])
        if simplices is None:
            dd = Delaunay(rvals[:,:2], qhull_options='')
            simplices = dd.simplices
        if debug:
            print 'number of cells', rvals.shape[0]
            print 'number of points in trimesh', dd.points.shape[0]

        tri = TriMesh()
        prefareaprop = VPropHandle()
        tri.add_property(prefareaprop, 'prefarea')
        # make a mesh out of this delaunay
        mverts = np.array(np.zeros(len(rvals)),dtype='object')
        for i, v  in enumerate(rvals):
            mv = tri.add_vertex(TriMesh.Point(*v))
            mverts[i] = mv
            tri.set_property(prefareaprop, mv, area[i])
        for f in simplices:
            tri.add_face(list(mverts[f])) 
        PV = PVmesh(tri)
        PV.vvals = vvals
        # We cheekily add this to the initialisation to avoid recovering it later
        PV.prefareaprop = prefareaprop
        return PV

if __name__=='__main__':

    print '-----------------------'
    print 'If you just want to run the analysis then use analyse_cells.py'
    print '-----------------------'

    epidat = '/home/dan/cells/run/soft_rpatch/epithelial_equilini.dat'

    import argparse
    import os.path as path

    parser = argparse.ArgumentParser()
 
    parser.add_argument("-i", "--input", type=str, default=epidat, help="Input dat file")
    parser.add_argument("-d", "--dir", type=str, default='/home/dan/tmp/', help="Output directory")
    #parser.add_argument("-o", "--output", type=str, default=epidat, help="Input dat file")

    args = parser.parse_args()
    epidat = args.input


    rdat = ReadData(epidat)
    pv = PVmesh.datbuild(rdat)

    # Handle K, and Gamma
    #nf = pv.mesh.n_faces()
    nf = pv.tri.n_vertices()
    # Could easily read these from a .conf file
    k = 1.
    gamma = 0.
    L = 0.
    K = np.full(nf, k)
    Gamma = np.full(nf, gamma)

    cl = pv._construct_cl_dict(L)
    pv.set_constants(K, Gamma, cl)

    pv.calculate_energy()
    #pv.calculate_forces()
    #pv.calculate_stress(np.zeros(3), 1.)
    wl = 1.
    pv._stress_setup(wl)
    #pv.stress_on_centres(wl , [1,100, 200])
    pv.stress_on_centres(wl)

    outdir = args.dir

    if pv.forces:
        mout = path.join(outdir, 'cellmesh.vtp')
        wr.writemeshenergy(pv, mout)

        tout = path.join(outdir, 'trimesh.vtp')
        wr.writetriforce(pv, tout)

    if pv.stress:
        sout = path.join(outdir, 'hardy_stress.vtp')
        wr.write_stress_ellipses(pv, sout, pv.stress)

